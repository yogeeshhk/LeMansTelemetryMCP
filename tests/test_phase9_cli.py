"""Local Phase 9 CLI and private HTTP behavior."""
import asyncio
from contextlib import asynccontextmanager
import json
import socket

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from lmu_mcp import cli
from lmu_mcp.database import Repository
from lmu_mcp.private_path import load_or_create, rotate
from lmu_mcp.server import create_server
from lmu_mcp.service import TelemetryService


@pytest.fixture
def anyio_backend(): return 'asyncio'


def test_private_path_is_stable_and_rotatable(tmp_path):
    first=load_or_create(tmp_path)
    assert len(first)>=32 and first==load_or_create(tmp_path)
    changed=rotate(tmp_path)
    assert changed!=first and changed==load_or_create(tmp_path)
    assert '/' not in changed


def test_occupied_port_is_reported_without_stopping_listener():
    listener=cli.bind_listener(0)
    try:
        port=listener.getsockname()[1]
        with pytest.raises(RuntimeError,match='unavailable'):
            cli.bind_listener(port)
        assert listener.fileno()>=0
    finally:
        listener.close()


def test_inspect_cli_rejects_absolute_session_id(recording,monkeypatch,capsys):
    monkeypatch.setattr(cli,'Repository',lambda:Repository(recording.parent))
    assert cli.main(['inspect',recording.name])==0
    report=json.loads(capsys.readouterr().out)
    assert report['session_id']==recording.name and report['tables']>0
    assert cli.main(['inspect',str(recording)])==2
    error=capsys.readouterr().err
    assert 'relative session ID' in error and str(recording.parent) not in error


@asynccontextmanager
async def private_http_server(recording):
    mcp=create_server(TelemetryService(Repository(recording.parent)),private_path='A'*32)
    listener=cli.bind_listener(0)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(),log_level='critical',access_log=False,lifespan='on'))
    task=asyncio.create_task(server.serve(sockets=[listener]))
    try:
        with anyio.fail_after(10):
            while not server.started:
                if task.done(): await task
                await anyio.sleep(.02)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True
        await asyncio.wait_for(task,10)
        listener.close()


@pytest.mark.anyio
async def test_private_http_mcp_handshake_and_host_origin_rejection(recording):
    async with private_http_server(recording) as base:
        url=base+'/'+'A'*32+'/mcp'
        async with streamable_http_client(url) as (read,write,_):
            async with ClientSession(read,write) as client:
                await client.initialize()
                names={tool.name for tool in (await client.list_tools()).tools}
                assert 'list_sessions' in names and 'compare_laps' in names
                result=await client.call_tool('list_sessions',{})
                assert not result.isError and result.structuredContent['total']==1
        async with httpx.AsyncClient() as client:
            assert (await client.post(base+'/mcp',json={})).status_code==404
            assert (await client.post(base+'/'+'B'*32+'/mcp',json={})).status_code==404
            assert (await client.post(url,headers={'Host':'evil.example'},json={})).status_code==421
            assert (await client.post(url,headers={'Origin':'https://evil.example'},json={})).status_code==403
            assert (await client.post(url,headers={'Origin':'https://chatgpt.com'},json={})).status_code!=403
