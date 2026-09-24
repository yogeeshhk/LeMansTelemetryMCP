"""Launcher lifecycle tests without publishing synthetic or private data."""
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from lmu_mcp import cli, launch


class FakeProcess:
    def __init__(self,name):
        self.name=name
        self.alive=True
        self.stopped=[]
    def poll(self): return None if self.alive else 1
    def terminate(self): self.stopped.append('terminate'); self.alive=False
    def wait(self,timeout): self.stopped.append('wait'); return 0
    def kill(self): self.stopped.append('kill'); self.alive=False


def test_launcher_waits_for_mcp_before_ngrok_and_cleans_owned_processes(monkeypatch,capsys):
    events=[]
    server=FakeProcess('server')
    tunnel=FakeProcess('tunnel')
    monkeypatch.setattr(launch,'preflight',lambda:'ngrok.exe')
    monkeypatch.setattr(launch,'load_or_create',lambda:'A'*32)
    def start(command):
        process=server if len(events)==0 else tunnel
        events.append('start '+process.name)
        return process
    monkeypatch.setattr(launch,'start_process',start)
    monkeypatch.setattr(launch,'wait_for_server',lambda proc,token:events.append('MCP ready'))
    monkeypatch.setattr(launch,'discover_tunnel',lambda proc:events.append('tunnel ready') or 'https://example.ngrok.app')
    def monitor(*args):
        events.append('monitor')
        raise KeyboardInterrupt
    monkeypatch.setattr(launch,'monitor',monitor)
    assert launch.run()==0
    assert events==['start server','MCP ready','start tunnel','tunnel ready','monitor']
    assert server.stopped==['terminate','wait'] and tunnel.stopped==['terminate','wait']
    assert 'https://example.ngrok.app/'+'A'*32+'/mcp' in capsys.readouterr().out


def test_failed_readiness_stops_only_started_server(monkeypatch):
    server=FakeProcess('server')
    started=[]
    monkeypatch.setattr(launch,'preflight',lambda:'ngrok.exe')
    monkeypatch.setattr(launch,'load_or_create',lambda:'A'*32)
    monkeypatch.setattr(launch,'start_process',lambda command:started.append(command) or server)
    def fail(*args): raise RuntimeError('handshake timeout')
    monkeypatch.setattr(launch,'wait_for_server',fail)
    with pytest.raises(RuntimeError,match='handshake timeout'):
        launch.run()
    assert len(started)==1 and server.stopped==['terminate','wait']


def test_monitor_detects_owned_process_exit():
    server=FakeProcess('server')
    tunnel=FakeProcess('tunnel')
    tunnel.alive=False
    with pytest.raises(RuntimeError,match='ngrok exited'):
        launch.monitor(server,tunnel)


def test_ngrok_discovery_accepts_only_https_for_owned_upstream(monkeypatch):
    process=FakeProcess('ngrok')
    response={'tunnels':[{'public_url':'https://wrong.ngrok.app','config':{'addr':'http://127.0.0.1:9999'}},
                         {'public_url':'https://wrong-host.ngrok.app','config':{'addr':'http://public.example:18765'}},
                         {'public_url':'https://right.ngrok.app','config':{'addr':'localhost:18765'}}]}
    monkeypatch.setattr(launch,'urlopen',lambda *args,**kwargs:io.BytesIO(json.dumps(response).encode()))
    assert launch.discover_tunnel(process,timeout=1)=='https://right.ngrok.app'


def test_launcher_preflight_rejects_occupied_port_without_processes(recording,monkeypatch):
    occupied=cli.bind_listener(0)
    port=occupied.getsockname()[1]
    monkeypatch.setattr(launch,'TELEMETRY_ROOT',recording.parent)
    monkeypatch.setattr(launch.shutil,'which',lambda name:'ngrok.exe')
    monkeypatch.setattr(launch.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
    monkeypatch.setattr(launch,'bind_listener',lambda:cli.bind_listener(port))
    try:
        with pytest.raises(RuntimeError,match='unavailable'):
            launch.preflight()
    finally:
        occupied.close()


def test_failed_tunnel_discovery_stops_both_owned_processes(monkeypatch):
    server=FakeProcess('server')
    tunnel=FakeProcess('tunnel')
    processes=iter([server,tunnel])
    monkeypatch.setattr(launch,'preflight',lambda:'ngrok.exe')
    monkeypatch.setattr(launch,'load_or_create',lambda:'A'*32)
    monkeypatch.setattr(launch,'start_process',lambda command:next(processes))
    monkeypatch.setattr(launch,'wait_for_server',lambda proc,token:None)
    def fail(*args): raise RuntimeError('no HTTPS tunnel')
    monkeypatch.setattr(launch,'discover_tunnel',fail)
    with pytest.raises(RuntimeError,match='no HTTPS tunnel'):
        launch.run()
    assert server.stopped==['terminate','wait']
    assert tunnel.stopped==['terminate','wait']
