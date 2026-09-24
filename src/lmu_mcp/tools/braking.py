"""Read-only, bounded braking-zone MCP tools."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, LapId, READ_ONLY

Onset = Annotated[float, Field(ge=1,le=100,allow_inf_nan=False,
    description='Brake onset threshold, percent of full brake. Must be no greater than min_peak_pct and greater than release_pct.')]
Release = Annotated[float, Field(ge=0,lt=100,allow_inf_nan=False,
    description='Brake release threshold, percent of full brake; must be below onset_pct.')]
Duration = Annotated[float, Field(ge=.1,le=10,allow_inf_nan=False,
    description='Minimum brake interval duration in seconds; short taps are excluded.')]
Peak = Annotated[float, Field(ge=1,le=100,allow_inf_nan=False,
    description='Minimum peak brake percent; must be at least onset_pct.')]
SpeedDrop = Annotated[float, Field(ge=0,le=150,allow_inf_nan=False,
    description='Minimum speed drop in km/h from brake onset to the interval minimum.')]
MatchDistance = Annotated[float, Field(ge=10,le=300,allow_inf_nan=False,
    description='Maximum difference between brake-start positions in metres for a zone match.')]


def register(mcp, runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_braking_zones(session_id: SessionId, lap: LapId, onset_pct: Onset=10.0,
                                release_pct: Release=5.0, min_duration_s: Duration=.3,
                                min_peak_pct: Peak=20.0, min_speed_drop_kph: SpeedDrop=5.0)->dict[str, Any]:
        """Use after list_laps and a lap summary when the question concerns braking. Detect zones from native brake samples, then return track-position, km/h speed, percent brake, seconds of covered ABS activity, and bounded throttle pickup. Thresholds are configurable and validated; tiny taps, unsupported timing and insufficient speed drop are excluded with counts. Partial onset/release is flagged. Official lap validity remains unknown. Compare two eligible laps with compare_braking_zones after inspecting each lap's conditions."""
        return await runner.call('get_braking_zones',session_id=session_id,lap=lap,
                                 onset_pct=onset_pct,release_pct=release_pct,
                                 min_duration_s=min_duration_s,min_peak_pct=min_peak_pct,
                                 min_speed_drop_kph=min_speed_drop_kph)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def compare_braking_zones(session_id: SessionId, lap_a: LapId, lap_b: LapId,
                                    onset_pct: Onset=10.0, release_pct: Release=5.0,
                                    min_duration_s: Duration=.3, min_peak_pct: Peak=20.0,
                                    min_speed_drop_kph: SpeedDrop=5.0,
                                    max_match_distance_m: MatchDistance=100.0)->dict[str, Any]:
        """Use after list_laps and both summaries for two benchmark-candidate laps in the same recording. Match fully observed braking zones in track order within a configurable start-position tolerance (10-300 m). Return A-minus-B differences for brake start/release/distance (m), initial/minimum speed (km/h), peak brake (%), throttle pickup (m) and covered ABS time (s), plus unmatched and excluded zones. A positive positional delta means A's event occurs later along the lap. Check quality, fuel, tyres and traffic; measured differences alone do not prove a driving cause."""
        return await runner.call('compare_braking_zones',session_id=session_id,lap_a=lap_a,lap_b=lap_b,
                                 onset_pct=onset_pct,release_pct=release_pct,
                                 min_duration_s=min_duration_s,min_peak_pct=min_peak_pct,
                                 min_speed_drop_kph=min_speed_drop_kph,
                                 max_match_distance_m=max_match_distance_m)
