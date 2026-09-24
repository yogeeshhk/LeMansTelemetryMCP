"""Synthetic Monza guide, distance failure, association and MCP coverage."""
from datetime import timedelta
import json
import sys

import duckdb
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
from tests.test_phase3_mcp import http_server


TRACK = "Autodromo Nazionale Monza"
LAYOUT = "Monza Curva Grande Circuit"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def monza_recording(corner_recording):
    # Synthetic 100 m intervals placed near Lesmo 1; no private telemetry is copied.
    with duckdb.connect(str(corner_recording)) as connection:
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='TrackName'", [TRACK]
        )
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='TrackLayout'", [LAYOUT]
        )
        connection.execute('UPDATE "Lap Dist" SET value=value+2300')
    return corner_recording


def test_approximate_identity_and_future_unique_association(monza_recording):
    service = TelemetryService(Repository(monza_recording.parent))
    guide = service.get_track_guide(monza_recording.name)
    assert guide["track"] == TRACK and guide["layout"] == LAYOUT
    assert guide["pack_status"] == "approximate" and guide["total"] == 11
    assert all(feature["status"] == "approximate" for feature in guide["features"])

    corner = service.get_corners(monza_recording.name, 1)["corners"][0]
    assert corner["name"] == "Curva di Lesmo 1"
    assert corner["track_feature"]["status"] == "approximate"
    comparison = service.compare_corner(monza_recording.name, 1, [1, 2])
    assert comparison["reference_corner"]["track_feature"]["status"] == "approximate"
    assert comparison["comparisons"][0]["corner"]["track_feature"]["status"] == "approximate"
    assert comparison["comparisons"][0]["lap_minus_reference"]["section_time_s"] > 0


def test_distance_reversal_blocks_corner_metrics_but_not_guide(monza_recording):
    with duckdb.connect(str(monza_recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=2300 WHERE rowid=50')
    service = TelemetryService(Repository(monza_recording.parent))
    guide = service.get_track_guide(monza_recording.name)
    assert guide["pack_status"] == "approximate" and guide["total"] == 11
    for operation in (
        lambda: service.get_corners(monza_recording.name, 1),
        lambda: service.compare_corner(monza_recording.name, 1, [1, 2]),
    ):
        with pytest.raises(InspectionError) as error:
            operation()
        assert error.value.code == "distance_reversal"
    report = service.calibration_report(monza_recording.name)
    assert any(item["lap"] == 1 and item["code"] == "distance_reversal"
               for item in report["unsupported_laps"])


def test_unknown_monza_variant_does_not_inherit_pack(monza_recording):
    with duckdb.connect(str(monza_recording)) as connection:
        connection.execute(
            "UPDATE metadata SET value='Monza Junior Circuit' WHERE key='TrackLayout'"
        )
    guide = TelemetryService(Repository(monza_recording.parent)).get_track_guide(
        monza_recording.name
    )
    assert guide["pack_status"] == "no_pack"
    assert guide["features"] == [] and guide["sources"] == []


async def check_monza(read, write):
    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
        await client.initialize()
        tools = await client.list_tools()
        guide_tool = next(tool for tool in tools.tools if tool.name == "get_track_guide")
        assert guide_tool.annotations.readOnlyHint
        features = []
        offset = 0
        while offset is not None:
            result = await client.call_tool(
                "get_track_guide",
                {"session_id": "race.duckdb", "offset": offset, "limit": 4},
            )
            assert not result.isError
            data = result.structuredContent
            assert json.loads(result.content[0].text) == data
            assert data["track"] == TRACK and data["layout"] == LAYOUT
            assert data["pack_status"] == "approximate" and data["total"] == 11
            assert "PRIVATE DRIVER" not in result.model_dump_json()
            assert "lap_time_s" not in result.model_dump_json()
            features.extend(data["features"])
            offset = data["next_offset"]
        assert len(features) == 11
        assert all(feature["status"] == "approximate" for feature in features)
        corners = await client.call_tool(
            "get_corners", {"session_id": "race.duckdb", "lap": 1}
        )
        assert corners.structuredContent["corners"][0]["name"] == "Curva di Lesmo 1"
        comparison = await client.call_tool(
            "compare_corner",
            {"session_id": "race.duckdb", "corner_id": 1, "laps": [1, 2]},
        )
        assert comparison.structuredContent["reference_corner"]["track_feature"]["status"] == "approximate"
        assert (await client.call_tool(
            "get_track_guide", {"session_id": "race.duckdb", "limit": 51}
        )).isError
        assert (await client.call_tool(
            "get_track_guide", {"session_id": "missing.duckdb"}
        )).isError


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_monza_actual_protocol(monza_recording, transport):
    if transport == "http":
        async with http_server(monza_recording) as url:
            async with streamable_http_client(url) as (read, write, _):
                await check_monza(read, write)
    else:
        script = (
            "from pathlib import Path; import sys; "
            "from lmu_mcp.database import Repository; "
            "from lmu_mcp.service import TelemetryService; "
            "from lmu_mcp.server import create_server; "
            "create_server(TelemetryService(Repository(Path(sys.argv[1])))).run(transport='stdio')"
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", script, str(monza_recording.parent)],
        )
        async with stdio_client(parameters) as (read, write):
            await check_monza(read, write)
