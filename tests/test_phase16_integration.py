"""Synthetic Spa identity, gaps, provenance and real MCP transports."""
from copy import deepcopy
from datetime import timedelta
import json
import sys
import duckdb
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from lmu_mcp.database import Repository, InspectionError
from lmu_mcp.service import TelemetryService
from lmu_mcp.track_knowledge import load_track_knowledge
from tests.test_phase3_mcp import http_server

SPA = 'Circuit de Spa-Francorchamps'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def spa_recording(corner_recording):
    # Synthetic 100 m intervals shifted to Campus, not a copy of a private lap.
    with duckdb.connect(str(corner_recording)) as connection:
        connection.execute("UPDATE metadata SET value=? WHERE key IN ('TrackName','TrackLayout')", [SPA])
        connection.execute('UPDATE "Lap Dist" SET value=value+4750')
        connection.execute("INSERT INTO metadata VALUES ('WeatherConditions','Heavy Rain')")
    return corner_recording


def test_weather_and_missing_speed_do_not_invent_targets(spa_recording):
    service = TelemetryService(Repository(spa_recording.parent))
    guide = service.get_track_guide(spa_recording.name)
    assert guide['total'] == 13
    assert service.get_session_info(spa_recording.name)['weather'] == 'Heavy Rain'
    assert any('wet' in n['applicability'].lower() or 'weather' in n['applicability'].lower()
               for n in guide['coaching'])
    with duckdb.connect(str(spa_recording)) as connection:
        connection.execute('UPDATE "Ground Speed" SET value=NULL WHERE rowid BETWEEN 45 AND 52')
    data = service.get_telemetry(spa_recording.name, 1, ['speed'], 4795, 4802, 1)
    assert data['channels']['speed'] == [None]*8
    assert service.get_track_guide(spa_recording.name) == guide
    json.dumps(data, allow_nan=False)


def test_reversal_blocks_metrics_but_not_general_guide(spa_recording):
    with duckdb.connect(str(spa_recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=4830 WHERE rowid=110')
    service = TelemetryService(Repository(spa_recording.parent))
    assert service.get_track_guide(spa_recording.name)['total'] == 13
    with pytest.raises(InspectionError) as error:
        service.get_corners(spa_recording.name, 2)
    assert error.value.code == 'distance_reversal'
    report = service.calibration_report(spa_recording.name)
    assert report['unsupported_laps'][0]['code'] == 'distance_reversal'


def test_source_and_coaching_edits_invalidate_without_changing_metrics(spa_recording, monkeypatch):
    current = deepcopy(load_track_knowledge(SPA, SPA))
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge', lambda *args: current)
    service = TelemetryService(Repository(spa_recording.parent))
    first = service.get_corners(spa_recording.name, 1)['corners'][0]
    assert first['track_feature']['feature_id'] == 'campus'
    comparison = service.compare_corner(spa_recording.name, 1, [1, 2])
    assert comparison['reference_corner']['name'] == 'Campus'
    assert comparison['comparisons'][0]['lap_minus_reference']['section_time_s'] > 0
    current['sources'][0]['retrieved'] = '2026-09-26'
    current['coaching'][0]['text'] = 'Revised synthetic review.'
    updated = service.get_corners(spa_recording.name, 1)['corners'][0]
    assert updated['track_feature']['sources'][0]['retrieved'] == '2026-09-26'
    assert updated['minimum_speed_kph'] == first['minimum_speed_kph']
    assert service.get_track_guide(spa_recording.name)['coaching'][0]['text'] == 'Revised synthetic review.'


async def check_spa(read, write):
    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
        await client.initialize()
        tools = await client.list_tools()
        tool = next(t for t in tools.tools if t.name == 'get_track_guide')
        assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
        features = []
        offset = 0
        while offset is not None:
            result = await client.call_tool('get_track_guide',
                {'session_id': 'race.duckdb', 'offset': offset, 'limit': 5})
            assert not result.isError
            data = result.structuredContent
            assert json.loads(result.content[0].text) == data
            assert len(result.model_dump_json().encode()) < 300000
            assert 'PRIVATE DRIVER' not in result.model_dump_json()
            assert 'lap_time_s' not in result.model_dump_json()
            assert data['layout'] == SPA and data['total'] == 13
            assert {n['topic'] for n in data['coaching']} == {'overview','setup','race','practice'}
            assert len(data['sources']) == 6
            features.extend(data['features'])
            offset = data['next_offset']
        assert len({f['feature_id'] for f in features}) == 13
        assert next(f for f in features if f['feature_id'] == 'eau-rouge-raidillon')['status'] == 'approximate'
        corners = await client.call_tool('get_corners', {'session_id': 'race.duckdb', 'lap': 1})
        assert not corners.isError
        assert corners.structuredContent['corners'][0]['name'] == 'Campus'
        comparison = await client.call_tool('compare_corner',
            {'session_id': 'race.duckdb', 'corner_id': 1, 'laps': [1,2]})
        assert not comparison.isError
        assert comparison.structuredContent['reference_corner']['name'] == 'Campus'
        for args in [{'session_id':'race.duckdb', 'limit':51}, {'session_id':'missing.duckdb'}]:
            assert (await client.call_tool('get_track_guide', args)).isError


@pytest.mark.anyio
@pytest.mark.parametrize('transport', ['stdio', 'http'])
async def test_spa_actual_protocol(spa_recording, transport):
    if transport == 'http':
        async with http_server(spa_recording) as url:
            async with streamable_http_client(url) as (read, write, _):
                await check_spa(read, write)
    else:
        script = ('from pathlib import Path; import sys; from lmu_mcp.database import Repository; '
                  'from lmu_mcp.service import TelemetryService; from lmu_mcp.server import create_server; '
                  'create_server(TelemetryService(Repository(Path(sys.argv[1])))).run(transport="stdio")')
        parameters = StdioServerParameters(command=sys.executable, args=['-c',script,str(spa_recording.parent)])
        async with stdio_client(parameters) as (read, write):
            await check_spa(read, write)
