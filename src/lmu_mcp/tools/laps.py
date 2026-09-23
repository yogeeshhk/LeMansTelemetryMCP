"""Lap-discovery and compact-summary MCP definitions."""
from typing import Any
from .common import SessionId, LapId, Offset, Limit, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_laps(session_id:SessionId,offset:Offset=0,limit:Limit=50)->dict[str, Any]:
        """List recorded lap intervals, times, maximum speeds, sample counts and quality flags. Use returned lap IDs. Partial intervals stay visible; official validity is null and benchmark_candidate is a separate heuristic. Page via next_offset."""
        return await runner.call('list_laps',session_id=session_id,offset=offset,limit=limit)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_lap_summary(session_id:SessionId,lap:LapId)->dict[str, Any]:
        """Use before detailed telemetry. Returns time-weighted speed/control metrics, brake application/gear-change counts, ABS/TC duration and available fuel/tyre context. No raw arrays. Missing channels yield null metrics and warnings; check coverage and lap flags before coaching."""
        return await runner.call('get_lap_summary',session_id=session_id,lap=lap)
