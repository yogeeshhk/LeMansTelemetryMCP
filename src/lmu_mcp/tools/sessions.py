"""Session/catalog MCP definitions; all reading stays in the service/repository."""
from typing import Annotated, Any
from pydantic import Field
from .common import SessionId, Offset, Limit, READ_ONLY


def register(mcp,runner):
    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_sessions(search: Annotated[str,Field(max_length=128)]='',offset:Offset=0,limit:Limit=20)->dict[str, Any]:
        """Start here to find recorded LMU sessions. Searches relative filenames, newest modified first; follow next_offset for more. Discovered does not guarantee readable: close active recordings before querying. No race-weekend identity is inferred."""
        return await runner.call('list_sessions',search=search,offset=offset,limit=limit)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_session_info(session_id:SessionId)->dict[str, Any]:
        """Use after choosing a session to inspect car/track, duration, available channels and schema warnings. Missing metadata is null. Follow with list_laps and summaries before requesting raw telemetry."""
        return await runner.call('get_session_info',session_id=session_id)

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def list_channels(session_id:SessionId)->dict[str, Any]:
        """Find exact canonical/raw channel names, component selectors, recorded units, sample counts, frequencies and min/max. Missing/ambiguous mappings are explicit. Producer units are not guessed; wheel order is unverified. Not every frequency supports reliable time alignment."""
        return await runner.call('list_channels',session_id=session_id)
