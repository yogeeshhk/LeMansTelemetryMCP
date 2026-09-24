"""Bounded, sourced track knowledge for a selected recording."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, Offset, READ_ONLY

GuideLimit = Annotated[int, Field(strict=True, ge=1, le=50,
    description='Maximum features on this page, 1-50.')]


def register(mcp, runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_track_guide(session_id: SessionId, offset: Offset=0,
                              limit: GuideLimit=50)->dict[str, Any]:
        """Use for a general track guide after resolving identity with get_session_info, or for named context during lap analysis. No eligible lap or valid distance path is required. Match the recording's exact track and layout; return at most 50 ordered sourced features and follow next_offset for more. Distances are metres and explicitly calibrated, approximate or unmatched, with source links and uncertainty. A no_pack result means no reviewed local guide exists; use unnamed measured corners instead. Coaching notes distinguish sourced context, general technique and hypotheses with applicability limits; explain their reasons before personal timing analysis when the user asks for a general guide. The guide is not proof of a driving or setup cause."""
        return await runner.call('get_track_guide',session_id=session_id,
                                 offset=offset,limit=limit)
