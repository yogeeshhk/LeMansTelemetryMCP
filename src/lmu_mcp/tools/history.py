"""Bounded corner history and source-gated setup experiments."""
from typing import Annotated, Any, Literal

from pydantic import Field

from .common import READ_ONLY, SessionId

HistoryCornerId = Annotated[int, Field(
    strict=True, ge=1, le=1000,
    description="corner_id from get_corners on a complete reference lap.",
)]
HistoryScope = Literal["recent", "general"]


def register(mcp, runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_corner_history(
        session_id: SessionId,
        corner_id: HistoryCornerId,
        scope: HistoryScope = "recent",
    ) -> dict[str, Any]:
        """Compare bounded recorded history for one measured corner after get_track_guide and get_corners. Use recent for the selected recording; use general only for up to five recordings with the same exact track, layout and car and at most 30 complete laps. Ranks at most three fastest distance-valid benchmark candidates and three disjoint slowest complete distance-valid laps using positive recorded Lap Time only. Returns disclosed selections, flags, repeated entry/mid/exit observations, unconfirmed path-deviation overlap, recording-level conditions and allowlisted current setup context. Setup experiments require repeated clean evidence, an available setting and an exact car-applicable primary source; otherwise the result asks for a driving test or driver feedback. Raw integer direction and wheel order are never guessed, and no setup file is written."""
        return await runner.call(
            "get_corner_history",
            session_id=session_id,
            corner_id=corner_id,
            scope=scope,
        )