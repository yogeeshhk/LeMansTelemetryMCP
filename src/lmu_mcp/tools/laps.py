"""Lap-discovery and compact-summary MCP definitions."""
from typing import Any
from .common import SessionId, LapId, Offset, Limit, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_laps(session_id:SessionId,offset:Offset=0,limit:Limit=50)->dict[str, Any]:
        """Use after get_session_info to choose lap IDs and benchmark candidates. Returns times, speeds, sample counts and quality flags; page via next_offset. Next call get_lap_summary for the coached lap and reference before compare_laps. If fewer than two candidates exist, summarize the available lap and explain the comparison limitation. Partial intervals stay visible; official validity is null, not inferred from eligibility."""
        return await runner.call('list_laps',session_id=session_id,offset=offset,limit=limit)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_lap_summary(session_id:SessionId,lap:LapId)->dict[str, Any]:
        """Use after list_laps for each chosen lap, before comparison or detailed telemetry. Returns compact speed/control metrics, brake/gear counts, ABS/TC durations and available fuel/tyre context. Check both laps for flags, coverage and condition differences. Next compare_laps at 20-50 m spacing, unless this summary already answers the question. Missing channels yield null metrics and warnings; no raw arrays."""
        return await runner.call('get_lap_summary',session_id=session_id,lap=lap)
