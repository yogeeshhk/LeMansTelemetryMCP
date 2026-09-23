import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import json
import socket
import sys

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp.exceptions import ToolError
from lmu_mcp.database import Repository
from lmu_mcp.service import TelemetryService
from lmu_mcp.server import create_server
from lmu_mcp.tools.common import Runner


@pytest.fixture
def anyio_backend(): return 'asyncio'


@asynccontextmanager
async def http_server(recording):
    mcp=create_server(TelemetryService(Repository(recording.parent)))
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen(128)
    listener.setblocking(False)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(),log_level='critical',access_log=False,lifespan='on'))
    task=asyncio.create_task(server.serve(sockets=[listener]))
    try:
        with anyio.fail_after(10):
            while not server.started:
                if task.done(): await task
                await anyio.sleep(.02)
        yield f'http://127.0.0.1:{port}/mcp'
    finally:
        server.should_exit=True
        await asyncio.wait_for(task,10)
        listener.close()


async def check_protocol(read,write):
    async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as client:
        initialized=await client.initialize()
        assert initialized.serverInfo.name=='Le Mans Ultimate Telemetry'
        tools=await client.list_tools()
        expected={'list_sessions','get_session_info','list_channels','list_laps','get_lap_summary','get_telemetry','compare_laps'}
        assert {t.name for t in tools.tools}==expected
        for tool in tools.tools:
            assert tool.annotations.readOnlyHint is True
            assert tool.annotations.destructiveHint is False
            assert tool.annotations.openWorldHint is False
            assert tool.outputSchema is not None
        calls=[('list_sessions',{}),('get_session_info',{'session_id':'race.duckdb'}),
               ('list_channels',{'session_id':'race.duckdb'}),('list_laps',{'session_id':'race.duckdb'}),
               ('get_lap_summary',{'session_id':'race.duckdb','lap':1}),
               ('get_telemetry',{'session_id':'race.duckdb','lap':1,'channels':['speed','gear'],'start_distance_m':45,'end_distance_m':55,'resolution_m':1}),
               ('compare_laps',{'session_id':'race.duckdb','laps':[1,2],'channels':['speed'],'start_distance_m':20,'end_distance_m':80,'resolution_m':10})]
        for name,args in calls:
            result=await client.call_tool(name,args)
            assert not result.isError,(name,result)
            assert isinstance(result.structuredContent,dict)
            assert len(result.model_dump_json().encode())<300000
            assert 'PRIVATE DRIVER' not in result.model_dump_json()
        invalid=await client.call_tool('get_lap_summary',{'session_id':'race.duckdb','lap':0})
        assert invalid.isError
        escaped=await client.call_tool('get_session_info',{'session_id':'../outside.duckdb'})
        assert escaped.isError and 'invalid_session' in escaped.content[0].text
        limited=await client.call_tool('get_telemetry',{'session_id':'race.duckdb','lap':1,'channels':['speed'],'start_distance_m':0,'end_distance_m':100000,'resolution_m':1})
        assert limited.isError and 'query_limit' in limited.content[0].text
        unknown=await client.call_tool('execute_sql',{'sql':'DROP TABLE Lap'})
        assert unknown.isError


@pytest.mark.anyio
async def test_real_stdio_protocol(recording):
    # Internal fixture injection, not a user-facing telemetry-directory option.
    script='from pathlib import Path; import sys; from lmu_mcp.database import Repository; from lmu_mcp.service import TelemetryService; from lmu_mcp.server import create_server; create_server(TelemetryService(Repository(Path(sys.argv[1])))).run(transport="stdio")'
    parameters=StdioServerParameters(command=sys.executable,args=['-c',script,str(recording.parent)])
    async with stdio_client(parameters) as (read,write):
        await check_protocol(read,write)


@pytest.mark.anyio
async def test_real_http_protocol_and_host_validation(recording):
    async with http_server(recording) as url:
        async with streamable_http_client(url) as (read,write,_):
            await check_protocol(read,write)
        async with httpx.AsyncClient() as client:
            response=await client.post(url,headers={'Host':'evil.example','Content-Type':'application/json'},json={})
            assert response.status_code==421


@pytest.mark.anyio
async def test_mcp_envelope_size_is_bounded(monkeypatch):
    class Fake:
        def large(self): return {'values':list(range(1000))}
    monkeypatch.setattr('lmu_mcp.config.MAX_OUTPUT_BYTES',2000)
    with pytest.raises(ToolError,match='response_limit'):
        await Runner(Fake()).call('large')


@pytest.mark.anyio
async def test_unexpected_errors_do_not_leak_paths():
    class Fake:
        def broken(self): raise RuntimeError('PRIVATE PATH AND SQL')
    with pytest.raises(ToolError) as e: await Runner(Fake()).call('broken')
    assert 'PRIVATE' not in str(e.value) and 'analysis_failed' in str(e.value)
