"""Fixed-port local CLI. Remote launcher orchestration lives in launch.py."""
import argparse
import asyncio
import json
import socket
import sys

import uvicorn

from .config import TELEMETRY_ROOT
from .database import InspectionError, Repository
from .diagnostics import diagnose, format_diagnostics
from .private_path import load_or_create, rotate
from .server import create_server

HOST = '127.0.0.1'
PORT = 18765


def bind_listener(port=PORT):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((HOST, port))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError as exc:
        listener.close()
        raise RuntimeError(f'Port {port} is unavailable on {HOST}; stop the existing listener and retry.') from exc


def serve_http(service=None, port=PORT, state_dir=None):
    if service is None and not TELEMETRY_ROOT.is_dir():
        raise RuntimeError('The fixed LMU telemetry directory is missing or unreadable.')
    token = load_or_create(state_dir)
    listener = bind_listener(port)
    try:
        app = create_server(service, private_path=token).streamable_http_app()
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port,
                                               log_level='warning', access_log=False, lifespan='on'))
        asyncio.run(server.serve(sockets=[listener]))
    finally:
        listener.close()


def inspect(session_id):
    report = Repository().inspect(session_id)
    print(json.dumps({'session_id':session_id, 'tables':len(report.tables),
                      'channels':sorted(name for name,source in report.channels.channels.items() if source),
                      'missing_channels':report.channels.missing,'warnings':report.warnings},
                     ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='lmu-mcp')
    commands = parser.add_subparsers(dest='command',required=True)
    inspection = commands.add_parser('inspect',help='Inspect one recording from the fixed telemetry directory.')
    inspection.add_argument('session_id')
    diagnosis = commands.add_parser('diagnose',help='Report read-only schema and lap support for one recording.')
    diagnosis.add_argument('session_id')
    commands.add_parser('serve',help='Serve private Streamable HTTP on 127.0.0.1:18765.')
    commands.add_parser('rotate-secret',help='Rotate the private MCP URL path; restart the server afterward.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            inspect(args.session_id)
        elif args.command == 'diagnose':
            print(format_diagnostics(diagnose(args.session_id)))
        elif args.command == 'serve':
            serve_http()
        elif args.command == 'rotate-secret':
            rotate()
            print('Private path rotated. Restart the server and reconnect ChatGPT with the new URL.')
        return 0
    except (InspectionError,RuntimeError,ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
