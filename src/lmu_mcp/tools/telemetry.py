"""Bounded telemetry and lap-comparison MCP definitions."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, LapId, Channels, Distance, Resolution, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_telemetry(session_id:SessionId,lap:LapId,channels:Channels|None=None,
                            start_distance_m:Distance=0.0,end_distance_m:Distance|None=None,
                            resolution_m:Resolution=2.0)->dict[str, Any]:
        """Zoom into a short distance range after summaries/coarse comparison. Returns column arrays aligned by distance, units, interpolation method and quality. Defaults: speed/brake/throttle/steering/gear. Continuous signals interpolate; discrete states hold. No extrapolation: gaps are null. Max 5000 points/20000 numeric values; increase spacing or reduce range on limit errors."""
        return await runner.call('get_telemetry',session_id=session_id,lap=lap,channels=channels,
                                 start_distance_m=start_distance_m,end_distance_m=end_distance_m,resolution_m=resolution_m)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def compare_laps(session_id:SessionId,laps:Annotated[list[LapId],Field(min_length=2,max_length=10)],
                           channels:Channels|None=None,start_distance_m:Distance=0.0,
                           end_distance_m:Distance|None=None,resolution_m:Resolution=20.0)->dict[str, Any]:
        """Compare benchmark candidate laps within one recording at coarse spacing first (default 20 m). Returns aligned arrays, cumulative interpolated elapsed-time/speed deltas and coarse brake/throttle onset differences. Positive A-minus-B time means A is slower. Not official timing or causal driving advice. Fuel/tyres/traffic can differ; narrow interesting sections with get_telemetry."""
        return await runner.call('compare_laps',session_id=session_id,laps=laps,channels=channels,
                                 start_distance_m=start_distance_m,end_distance_m=end_distance_m,resolution_m=resolution_m)
