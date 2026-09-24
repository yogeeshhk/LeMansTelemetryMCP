"""Own the Windows MCP and ngrok child processes for one personal session."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .cli import HOST, PORT, bind_listener
from .config import TELEMETRY_ROOT
from .private_path import load_or_create

INSPECTOR_HOST = '127.0.0.1'
INSPECTOR_PORT = 4040


def preflight():
    if not TELEMETRY_ROOT.is_dir():
        raise RuntimeError('The fixed LMU telemetry directory is missing or unreadable.')
    if not (Path.cwd()/'ngrok-traffic-policy.yml').is_file():
        raise RuntimeError('Run startLeMansMCP.ps1 from its project directory; ngrok policy is missing.')
    ngrok = shutil.which('ngrok')
    if not ngrok:
        raise RuntimeError('ngrok is unavailable. Install ngrok and add it to PATH.')
    for args, failure in (([ngrok,'version'], 'ngrok executable failed; verify its installation.'),
                          ([ngrok,'config','check'], 'ngrok configuration is invalid; run ngrok config check.')):
        try:
            result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise RuntimeError('ngrok could not be checked; verify its installation and configuration.') from exc
        if result.returncode != 0:
            raise RuntimeError(failure)
    listener=bind_listener()
    listener.close()
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as check:
        if check.connect_ex((INSPECTOR_HOST,INSPECTOR_PORT)) == 0:
            raise RuntimeError('ngrok inspector port 4040 is occupied; stop that agent and retry.')
    return ngrok


def start_process(command):
    return subprocess.Popen(command,cwd=str(Path.cwd()),stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


async def probe_mcp(token):
    url=f'http://{HOST}:{PORT}/{token}/mcp'
    async with asyncio.timeout(4):
        async with streamable_http_client(url) as (read,write,_):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=3)) as client:
                await client.initialize()
                tools=await client.list_tools()
                if not tools.tools:
                    raise RuntimeError('MCP server advertised no tools.')


def wait_for_server(process,token,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError('MCP server exited before readiness; run lmu-mcp serve for details.')
        try:
            asyncio.run(probe_mcp(token))
            return
        except Exception:
            time.sleep(.25)
    raise RuntimeError('MCP server did not complete a local protocol handshake before timeout.')


def discover_tunnel(process,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError('ngrok exited before exposing a tunnel; check ngrok authentication and configuration.')
        try:
            with urlopen(f'http://{INSPECTOR_HOST}:{INSPECTOR_PORT}/api/tunnels',timeout=1) as response:
                tunnels=json.load(response).get('tunnels',[])
            for tunnel in tunnels:
                upstream_address=tunnel.get('config',{}).get('addr','')
                upstream=urlsplit(upstream_address if '://' in upstream_address
                                  else f'http://{upstream_address}')
                public=tunnel.get('public_url','')
                public_url=urlsplit(public)
                if (upstream.hostname in {'127.0.0.1','localhost'} and upstream.port==PORT
                        and public_url.scheme=='https' and public_url.hostname):
                    return public.rstrip('/')
        except (OSError,ValueError,KeyError,TypeError):
            pass
        time.sleep(.25)
    raise RuntimeError('ngrok did not expose an HTTPS tunnel for port 18765 before timeout.')


def monitor(server,tunnel):
    while True:
        if server.poll() is not None:
            raise RuntimeError('MCP server exited unexpectedly; the tunnel is stopping.')
        if tunnel.poll() is not None:
            raise RuntimeError('ngrok exited unexpectedly; the MCP server is stopping.')
        time.sleep(.5)


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run():
    ngrok=preflight()
    token=load_or_create()
    server=None
    tunnel=None
    try:
        server=start_process([sys.executable,'-m','lmu_mcp.cli','serve'])
        wait_for_server(server,token)
        tunnel=start_process([ngrok,'http',str(PORT),'--traffic-policy-file',str(Path.cwd()/'ngrok-traffic-policy.yml'),'--inspect=false'])
        public=discover_tunnel(tunnel)
        print(f'ChatGPT MCP URL: {public}/{token}/mcp',flush=True)
        print('Keep this URL private. Press Ctrl+C to stop the owned server and tunnel.',flush=True)
        monitor(server,tunnel)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_owned(tunnel)
        stop_owned(server)


def main():
    try:
        return run()
    except (RuntimeError,OSError) as error:
        print(str(error),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
