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
        expected={'list_sessions','get_session_info','list_channels','list_laps','get_lap_summary','get_telemetry','compare_laps','get_braking_zones','compare_braking_zones','get_corners','compare_corner'}
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
               ('compare_laps',{'session_id':'race.duckdb','laps':[1,2],'channels':['speed'],'start_distance_m':20,'end_distance_m':80,'resolution_m':10}),
               ('get_braking_zones',{'session_id':'race.duckdb','lap':1}),
               ('compare_braking_zones',{'session_id':'race.duckdb','lap_a':1,'lap_b':2}),
               ('get_corners',{'session_id':'race.duckdb','lap':1}),
               ('compare_corner',{'session_id':'race.duckdb','corner_id':1,'laps':[1,2]})]
        for name,args in calls:
            result=await client.call_tool(name,args)
            assert not result.isError,(name,result)
            assert isinstance(result.structuredContent,dict)
            assert json.loads(result.content[0].text)==result.structuredContent
            assert len(result.content[0].text)<len(json.dumps(result.structuredContent,indent=2))
            assert len(result.model_dump_json().encode())<300000
            assert 'PRIVATE DRIVER' not in result.model_dump_json()
        corners=await client.call_tool('get_corners',{'session_id':'race.duckdb','lap':1})
        assert corners.structuredContent['total']==1
        comparison=await client.call_tool('compare_corner',{'session_id':'race.duckdb','corner_id':1,'laps':[1,2]})
        assert len(comparison.structuredContent['comparisons'])==1
        invalid_corner=await client.call_tool('compare_corner',{'session_id':'race.duckdb','corner_id':999,'laps':[1,2]})
        assert invalid_corner.isError and 'unknown_corner' in invalid_corner.content[0].text
        invalid=await client.call_tool('get_lap_summary',{'session_id':'race.duckdb','lap':0})
        assert invalid.isError
        escaped=await client.call_tool('get_session_info',{'session_id':'../outside.duckdb'})
        assert escaped.isError and 'invalid_session' in escaped.content[0].text
        limited=await client.call_tool('get_telemetry',{'session_id':'race.duckdb','lap':1,'channels':['speed'],'start_distance_m':0,'end_distance_m':100000,'resolution_m':1})
        assert limited.isError and 'query_limit' in limited.content[0].text
        unknown=await client.call_tool('execute_sql',{'sql':'DROP TABLE Lap'})
        assert unknown.isError


@pytest.mark.anyio
async def test_real_stdio_protocol(corner_recording):
    recording=corner_recording
    # Internal fixture injection, not a user-facing telemetry-directory option.
    script='from pathlib import Path; import sys; from lmu_mcp.database import Repository; from lmu_mcp.service import TelemetryService; from lmu_mcp.server import create_server; create_server(TelemetryService(Repository(Path(sys.argv[1])))).run(transport="stdio")'
    parameters=StdioServerParameters(command=sys.executable,args=['-c',script,str(recording.parent)])
    async with stdio_client(parameters) as (read,write):
        await check_protocol(read,write)


@pytest.mark.anyio
async def test_real_http_protocol_and_host_validation(corner_recording):
    recording=corner_recording
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


@pytest.mark.anyio
async def test_progressive_workflow_locates_local_loss(recording):
    import duckdb
    # Synthetic lap 2 loses exactly two seconds between 40 and 60 metres.
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=CASE WHEN rowid<140 THEN (rowid-100) WHEN rowid<180 THEN 40+(rowid-140)*0.5 ELSE 60+(rowid-180) END WHERE rowid>=100 AND rowid<220')
        connection.execute('UPDATE "Ground Speed" SET value=CASE WHEN rowid>=140 AND rowid<180 THEN 18 ELSE 36 END WHERE rowid>=100 AND rowid<220')
    async with http_server(recording) as url:
        async with streamable_http_client(url) as (read,write,_):
            async with ClientSession(read,write) as client:
                await client.initialize()
                async def call(name,**arguments):
                    result=await client.call_tool(name,arguments)
                    assert not result.isError,result
                    assert len(result.model_dump_json().encode())<300000
                    return result.structuredContent
                sessions=await call('list_sessions')
                session_id=sessions['sessions'][0]['session_id']
                info=await call('get_session_info',session_id=session_id)
                assert info['number_of_laps']==2
                listing=await call('list_laps',session_id=session_id)
                candidates=sorted((lap for lap in listing['laps'] if lap['benchmark_candidate']),key=lambda lap:lap['lap_time_s'],reverse=True)
                chosen=[lap['lap'] for lap in candidates]
                assert chosen==[2,1]
                for lap in chosen:
                    await call('get_lap_summary',session_id=session_id,lap=lap)
                coarse=await call('compare_laps',session_id=session_id,laps=chosen,channels=['speed'],resolution_m=20)
                distances=coarse['distance_m']
                delta=coarse['deltas'][0]['elapsed_delta_a_minus_b_s']
                intervals=[(delta[i+1]-delta[i],distances[i],distances[i+1]) for i in range(len(distances)-1) if delta[i] is not None and delta[i+1] is not None]
                loss,start,end=max(intervals)
                assert (loss,start,end)==pytest.approx((2,40,60))
                details=[]
                for lap in chosen:
                    details.append(await call('get_telemetry',session_id=session_id,lap=lap,channels=['speed'],start_distance_m=start-10,end_distance_m=end+10,resolution_m=1))
                assert details[0]['distance_m']==details[1]['distance_m']==list(range(30,71))
                assert all(detail['units']['speed']=='km/h' for detail in details)
                durations=[detail['elapsed_s'][-1]-detail['elapsed_s'][0] for detail in details]
                assert durations[0]-durations[1]==pytest.approx(2)


@pytest.mark.anyio
async def test_braking_tools_return_known_zone_and_validation_error(recording):
    import duckdb
    with duckdb.connect(str(recording)) as connection:
        connection.execute("""UPDATE "Ground Speed" SET value = CASE
            WHEN rowid BETWEEN 20 AND 40 THEN 100 - (rowid - 20) * 2
            WHEN rowid BETWEEN 124 AND 148 THEN 95 - (rowid - 124) * 1.7
            ELSE 100 END""")
    async with http_server(recording) as url:
        async with streamable_http_client(url) as (read,write,_):
            async with ClientSession(read,write) as client:
                await client.initialize()
                zones=await client.call_tool('get_braking_zones',{'session_id':'race.duckdb','lap':1})
                assert not zones.isError and len(zones.structuredContent['zones'])==1
                assert zones.structuredContent['zones'][0]['start_distance_m']==20
                comparison=await client.call_tool('compare_braking_zones',
                                                  {'session_id':'race.duckdb','lap_a':1,'lap_b':2})
                assert not comparison.isError and len(comparison.structuredContent['matches'])==1
                assert comparison.structuredContent['matches'][0]['a_minus_b']['initial_speed_kph']==5
                invalid=await client.call_tool('get_braking_zones',
                                               {'session_id':'race.duckdb','lap':1,'onset_pct':4,'release_pct':5})
                assert invalid.isError and 'invalid_threshold' in invalid.content[0].text
