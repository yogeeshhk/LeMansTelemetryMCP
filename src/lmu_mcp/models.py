"""Shared data contracts without database or MCP dependencies."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    kind: str
    columns: tuple[Column, ...]
    row_count: int | None
    # Samples belong only to local inspection output, never schema matching logic.
    samples: tuple[tuple, ...] = ()


@dataclass(frozen=True)
class Source:
    schema: str
    table: str
    value_columns: tuple[str, ...]
    timestamp_column: str | None
    kind: str
    unit: str | None = None
    frequency_hz: float | None = None


@dataclass
class ChannelMap:
    channels: dict[str, Source | None]
    ambiguous: dict[str, list[Source]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Inspection:
    session_id: str
    tables: list[Table]
    channels: ChannelMap
    catalog: dict[str, dict]
    warnings: list[str]

    def to_dict(self):
        return asdict(self)
