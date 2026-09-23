"""Session/catalog MCP definitions; all reading stays in the service/repository."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, Offset, Limit, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_sessions(search: Annotated[str,Field(max_length=128)]='',offset:Offset=0,limit:Limit=20)->dict[str, Any]:
        """Start here when the intended recording is not already known. Filter relative filenames, page via next_offset, then pass the chosen session_id to get_session_info. Newest modified is not necessarily the intended race. Discovered does not guarantee readable; close active recordings before querying. Do not request telemetry arrays at this stage or infer race-weekend identity."""
        return await runner.call('list_sessions',search=search,offset=offset,limit=limit)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_session_info(session_id:SessionId)->dict[str, Any]:
        """Use after list_sessions or a user-selected session to confirm car/track, duration, available channels and schema warnings. Missing metadata is null. Next call list_laps; use list_channels only if a needed signal or unit is unclear. Stay with metadata and summaries before requesting telemetry arrays."""
        return await runner.call('get_session_info',session_id=session_id)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_channels(session_id:SessionId)->dict[str, Any]:
        """Use when a signal name/unit is unknown or a query reports a missing channel; this is an optional branch after get_session_info. Find exact canonical/raw names, component selectors, units, frequencies and extrema, then return to the pending summary/comparison with only needed channels. Do not automatically query every listed channel. Missing/ambiguous mappings are explicit; wheel order and unsupported timing are not guessed."""
        return await runner.call('list_channels',session_id=session_id)
