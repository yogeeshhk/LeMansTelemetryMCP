"""Shared validated tool parameters and bounded worker execution."""
from functools import partial
import json
from typing import Annotated
import anyio
from pydantic import Field
from .. import config
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from mcp.server.fastmcp.exceptions import ToolError
from ..database import InspectionError

SessionId = Annotated[str, Field(min_length=1,max_length=512,description='Relative recording ID returned by list_sessions.')]
LapId = Annotated[int, Field(strict=True,ge=1,description='Unique interval ID returned by list_laps, not an assumed game lap number.')]
ChannelName = Annotated[str, Field(min_length=1,max_length=128)]
Channels = Annotated[list[ChannelName], Field(min_length=1,max_length=20,description='Names from list_channels; use name:value1 for a component.')]
Distance = Annotated[float, Field(ge=0,le=200000,allow_inf_nan=False,description='Lap distance in metres.')]
Resolution = Annotated[float, Field(ge=.1,le=200000,allow_inf_nan=False,description='Distance spacing in metres. Increase this for a coarser and smaller response.')]
Offset = Annotated[int, Field(strict=True,ge=0,le=100000)]
Limit = Annotated[int, Field(strict=True,ge=1,le=100)]
READ_ONLY = ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)


class Runner:
    def __init__(self,service):
        self.service=service
        self.limiter=anyio.CapacityLimiter(2)

    async def call(self,method,**arguments):
        try:
            result = await anyio.to_thread.run_sync(partial(getattr(self.service,method),**arguments),limiter=self.limiter)
            compact = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            envelope = CallToolResult(content=[TextContent(type='text', text=compact)],
                                      structuredContent=result, isError=False)
            if len(envelope.model_dump_json(exclude_none=True).encode('utf-8'))+2048 > config.MAX_OUTPUT_BYTES:
                raise InspectionError('response_limit','MCP response is too large; reduce channels/range or increase resolution_m.')
            return envelope
        except InspectionError as exc:
            raise ToolError(json.dumps({'code':exc.code,'message':str(exc)},ensure_ascii=True)) from None
        except Exception:
            # Do not expose DuckDB exception strings, paths, SQL or Python tracebacks remotely.
            raise ToolError(json.dumps({'code':'analysis_failed','message':'Telemetry could not be analysed safely. Check recording availability and schema diagnostics; try a smaller query.'})) from None
