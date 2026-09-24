"""Bounded telemetry and lap-comparison MCP definitions."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, LapId, Channels, Distance, Resolution, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_telemetry(session_id:SessionId,lap:LapId,channels:Channels|None=None,
                            start_distance_m:Distance=0.0,end_distance_m:Annotated[Distance|None,Field(description="For a detailed query, supply an explicit section end in metres. Null uses available lap coverage; reserve that for coarse overviews.")]=None,
                            resolution_m:Resolution=2.0)->dict[str, Any]:
        """Use last to investigate one section identified by summaries/coarse compare_laps, or a distance range explicitly requested by the user. Set both distance bounds, usually covering 200-500 m, and request only relevant channels at 1-2 m spacing. For lap comparisons query the same section on both laps. Do not begin with a full lap at high resolution. Returns column arrays, units, methods and quality; gaps stay null. Increase resolution_m or narrow the range on limit errors; stop refining once the question is answered."""
        return await runner.call('get_telemetry',session_id=session_id,lap=lap,channels=channels,
                                 start_distance_m=start_distance_m,end_distance_m=end_distance_m,resolution_m=resolution_m)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def compare_laps(session_id:SessionId,laps:Annotated[list[LapId],Field(min_length=2,max_length=10)],
                           channels:Channels|None=None,start_distance_m:Distance=0.0,
                           end_distance_m:Annotated[Distance|None,Field(description="For a detailed query, supply an explicit section end in metres. Null uses available lap coverage; reserve that for coarse overviews.")]=None,resolution_m:Resolution=20.0)->dict[str, Any]:
        """Use after list_laps and get_lap_summary for each selected candidate. Start with two laps, a few channels and 20-50 m spacing (default 20 m); put the coached lap first and reference second. Positive A-minus-B elapsed delta means A is slower. Identify local loss as delta(end)-delta(start) over a covered section, not the largest cumulative value. Then get_telemetry on that section for both laps with explicit bounds and 1-2 m spacing. Control-onset differences are coarse hints; the dedicated braking tools can refine brake differences after this coarse comparison; named-corner tools remain unavailable. Conditions can differ; deltas do not establish causation."""
        return await runner.call('compare_laps',session_id=session_id,laps=laps,channels=channels,
                                 start_distance_m=start_distance_m,end_distance_m=end_distance_m,resolution_m=resolution_m)
