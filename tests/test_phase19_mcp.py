"""Actual stdio and HTTP coverage for bounded corner history."""
from datetime import timedelta
import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from tests.test_phase19_service import put_metadata, setup_value
from tests.test_phase3_mcp import http_server


@pytest.fixture
def history_protocol_recording(corner_recording):
    setup = json.dumps({
        "VM_DIFF_PRELOAD": setup_value("VM_DIFF_PRELOAD", 2),
        "WM_PRESSURE-W_FL": setup_value("WM_PRESSURE-W_FL", 99),
    })
    put_metadata(corner_recording, CarName="Ligier JS P325",
                 WeatherConditions="Dry", SessionType="Practice", CarSetup=setup)
    return corner_recording


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def check_history(read, write):
    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
        await client.initialize()
        tools = await client.list_tools()
        tool = next(item for item in tools.tools if item.name == "get_corner_history")
        assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
        assert tool.annotations.openWorldHint is False and tool.outputSchema is not None
        for scope in ("recent", "general"):
            result = await client.call_tool(
                "get_corner_history",
                {"session_id": "race.duckdb", "corner_id": 1, "scope": scope},
            )
            assert not result.isError
            data = result.structuredContent
            assert json.loads(result.content[0].text) == data
            assert data["scope"] == scope and data["selection"]["laps"]
            assert data["selection"]["method"].endswith("no boundary-duration ranking.")
            assert data["setup_context"]["settings"][0]["setting_id"] == "VM_DIFF_PRELOAD"
            assert data["experiments"] == []
            assert "PRIVATE DRIVER" not in result.model_dump_json()
            assert len(result.model_dump_json().encode()) < 300000
        for arguments in (
            {"session_id": "race.duckdb", "corner_id": 1, "scope": "all"},
            {"session_id": "race.duckdb", "corner_id": 0},
            {"session_id": "race.duckdb", "corner_id": 999},
            {"session_id": "missing.duckdb", "corner_id": 1},
        ):
            assert (await client.call_tool("get_corner_history", arguments)).isError


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_corner_history_actual_protocol(history_protocol_recording, transport):
    if transport == "http":
        async with http_server(history_protocol_recording) as url:
            async with streamable_http_client(url) as (read, write, _):
                await check_history(read, write)
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
            args=["-c", script, str(history_protocol_recording.parent)],
        )
        async with stdio_client(parameters) as (read, write):
            await check_history(read, write)