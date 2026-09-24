"""Bounded unconfirmed path-deviation hotspots."""
from typing import Annotated, Any, Literal

from pydantic import Field

from .common import Offset, READ_ONLY, SessionId

ExcursionLimit = Annotated[int, Field(
    strict=True, ge=1, le=50,
    description="Maximum hotspot rows on this page, 1-50.",
)]
ExcursionScope = Literal["recent", "general"]


def register(mcp, runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_excursion_hotspots(
        session_id: SessionId,
        scope: ExcursionScope = "recent",
        offset: Offset = 0,
        limit: ExcursionLimit = 50,
    ) -> dict[str, Any]:
        """Find repeated unconfirmed path deviations after resolving a session. Use recent for complete laps in the selected recording; use general only when bounded history for the same exact track, layout and car is useful. General examines at most five recordings and 30 complete laps. Complete flagged laps contribute event counts but are never clean pace benchmarks. Results require sustained Path Lateral beyond same-side Track Edge with validated metre/time/distance coverage, split gaps and explicit truncation. Surface codes and GPS do not trigger events. Treat hotspots as uncertain vehicle-centre observations, never official track-limit violations; inspect coverage, confidence and optional sourced feature before coaching."""
        return await runner.call(
            "get_excursion_hotspots",
            session_id=session_id,
            scope=scope,
            offset=offset,
            limit=limit,
        )
