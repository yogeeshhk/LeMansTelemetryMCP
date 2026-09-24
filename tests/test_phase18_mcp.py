"""Actual stdio and HTTP coverage for bounded excursion hotspots."""
from datetime import timedelta
import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from tests.test_phase18_service import add_excursion_signals
from tests.test_phase3_mcp import http_server


@pytest.fixture
def excursion_protocol_recording(recording):
    add_excursion_signals(recording)
    return recording


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def check_excursions(read, write):
    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
        await client.initialize()
        tools = await client.list_tools()
        tool = next(item for item in tools.tools if item.name == "get_excursion_hotspots")
        assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
        for scope in ("recent", "general"):
            result = await client.call_tool(
                "get_excursion_hotspots",
                {"session_id": "race.duckdb", "scope": scope, "limit": 1},
            )
            assert not result.isError
            data = result.structuredContent
            assert json.loads(result.content[0].text) == data
            assert data["scope"] == scope
            assert data["confidence"] == "unconfirmed_path_deviation"
            assert data["event_count"] == 3
            assert len(data["hotspots"]) == 1 and data["next_offset"] == 1
            assert "official track-limit" in data["method"]
            assert "PRIVATE DRIVER" not in result.model_dump_json()
            assert len(result.model_dump_json().encode()) < 300000
        for arguments in (
            {"session_id": "race.duckdb", "scope": "all"},
            {"session_id": "race.duckdb", "limit": 51},
            {"session_id": "missing.duckdb"},
        ):
            assert (await client.call_tool("get_excursion_hotspots", arguments)).isError


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_excursion_actual_protocol(excursion_protocol_recording, transport):
    if transport == "http":
        async with http_server(excursion_protocol_recording) as url:
            async with streamable_http_client(url) as (read, write, _):
                await check_excursions(read, write)
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
            args=["-c", script, str(excursion_protocol_recording.parent)],
        )
        async with stdio_client(parameters) as (read, write):
            await check_excursions(read, write)
