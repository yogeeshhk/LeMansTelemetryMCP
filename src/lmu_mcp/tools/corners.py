"""Read-only corner discovery and bounded candidate-lap comparison."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, LapId, Offset, READ_ONLY

CornerId = Annotated[int, Field(strict=True,ge=1,le=1000,
    description='corner_id from get_corners on the first (reference) lap.')]
CornerLimit = Annotated[int, Field(strict=True,ge=1,le=50,
    description='Maximum corner rows on this page, 1-50.')]
CornerLaps = Annotated[list[LapId], Field(min_length=2,max_length=5,
    description='Two to five distinct benchmark-candidate lap IDs from list_laps; first is the reference.')]


def register(mcp, runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_corners(session_id: SessionId, lap: LapId, offset: Offset=0,
                          limit: CornerLimit=50)->dict[str, Any]:
        """Use after list_laps and a lap summary to discover approximate corner ranges for one lap. Follow next_offset for more than 50 rows. Exact track/layout manual JSON definitions override automatic detection; otherwise verified steering (%), lateral acceleration (G) and speed (km/h) identify sustained turns. Returns unnamed automatic ranges and entry/minimum/exit speed (km/h), distance positions (m), approximate section time (s), control/ABS/TC metrics and quality flags. The minimum-speed position approximates the apex, not a surveyed track apex. Requires a validated increasing lap-distance path; missing or ambiguous channels can make automatic detection unavailable. Use compare_corner for candidate laps, then short-range get_telemetry if more detail is needed."""
        return await runner.call('get_corners',session_id=session_id,lap=lap,offset=offset,limit=limit)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def compare_corner(session_id: SessionId, corner_id: CornerId,
                             laps: CornerLaps)->dict[str, Any]:
        """Use after get_corners on the first lap and summaries of 2-5 benchmark-candidate laps. Return the first lap as reference, matched corner metrics on later laps, and lap-minus-reference differences. Manual corners match by exact ID; unnamed automatic corners match nearest start within 100 m and can be unmatched. Distances are metres, speeds km/h, time seconds and steering percent. Brake point, turn-in, apex/minimum-speed position, throttle pickup/full throttle, entry/exit speed, approximate section time and ABS/TC activity are included where covered; nulls and quality flags limit conclusions. Check fuel/tyres and coverage before coaching; a positional or time difference alone does not establish cause."""
        return await runner.call('compare_corner',session_id=session_id,corner_id=corner_id,laps=laps)
