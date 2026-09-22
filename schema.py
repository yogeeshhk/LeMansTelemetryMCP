"""Transport-independent source descriptions and conservative channel mapping."""
from dataclasses import dataclass, field
import re


def normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


ALIASES = {
    "timestamp": ("GPS Time", "timestamp", "time", "session_time", "ts"),
    "lap_number": ("Lap", "lap_number", "lap_index"),
    "lap_distance": ("Lap Dist", "lap_distance", "lap_distance_m"),
    "speed": ("Ground Speed", "speed", "speed_kph", "vehicle_speed"),
    "throttle": ("Throttle Pos", "throttle", "throttle_position"),
    "brake": ("Brake Pos", "brake", "brake_position"),
    "steering": ("Steering Pos", "steering", "steering_position"),
    "gear": ("Gear",),
    "rpm": ("Engine RPM", "rpm"),
    "longitudinal_acceleration": ("G Force Long", "longitudinal_acceleration", "accel_long"),
    "lateral_acceleration": ("G Force Lat", "lateral_acceleration", "accel_lat"),
    "yaw_rate": ("yaw_rate",),
    "wheel_speeds": ("Wheel Speed", "wheel_speeds"),
    "abs": ("ABS", "abs_active"),
    "tc": ("TC", "traction_control_active"),
    "brake_bias": ("Brake Bias Rear", "brake_bias_rear"),
    "tyre_wear": ("Tyres Wear", "tyre_wear", "tire_wear"),
    "tyre_pressure": ("TyresPressure", "tyre_pressure", "tire_pressure"),
    "tyre_temperature": ("TyresCarcassTemp", "tyre_carcass_temperature", "tire_carcass_temperature"),
}


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


def numeric(column: Column) -> bool:
    return column.data_type.split("(")[0] in {
        "BOOLEAN", "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
        "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
        "FLOAT", "DOUBLE", "DECIMAL", "REAL",
    }


def map_channels(tables: list[Table], catalog: dict[str, dict]) -> ChannelMap:
    """Map inspected catalogs or wide numeric columns; never guess ambiguous matches.

    Aliases recognize names, not units. No physical conversion or time reconstruction
    is performed. Unit-less wide sources remain unit-less until verified separately.
    """
    candidates: list[tuple[str, Source]] = []
    warnings = []
    for t in tables:
        if t.kind != "BASE TABLE":
            continue
        columns = {c.name: c for c in t.columns}
        if t.schema == "main" and t.name in catalog:
            info = catalog[t.name]
            values = tuple(n for n in ("value", "value1", "value2", "value3", "value4") if n in columns)
            if values not in [("value",), ("value1", "value2", "value3", "value4")] or not all(numeric(columns[n]) for n in values):
                warnings.append(f"Unsupported value columns for catalog signal: {t.name}")
                continue
            event = info["kind"] == "event"
            if event and ("ts" not in columns or not numeric(columns["ts"])):
                warnings.append(f"Missing numeric event timestamp: {t.name}")
                continue
            candidates.append((t.name, Source(t.schema, t.name, values, "ts" if event else None,
                                               info["kind"], info.get("unit"), info.get("frequency_hz"))))
            continue
        if t.name in {"channelsList", "eventsList", "metadata"}:
            continue
        # Wide schema fallback: data columns are meaningful names in one table.
        time_cols = [c.name for c in t.columns if numeric(c) and normalized(c.name) in {normalized(n) for n in ALIASES["timestamp"]}]
        timestamp = time_cols[0] if len(time_cols) == 1 else None
        if len(time_cols) > 1:
            warnings.append(f"Ambiguous time columns in {t.schema}.{t.name}")
        for c in t.columns:
            if numeric(c):
                candidates.append((c.name, Source(t.schema, t.name, (c.name,), timestamp, "wide")))
    mapping = ChannelMap(channels={}, warnings=warnings)
    for canonical, aliases in ALIASES.items():
        names = {normalized(a) for a in aliases}
        found = [src for name, src in candidates if normalized(name) in names]
        mapping.channels[canonical] = found[0] if len(found) == 1 else None
        if not found:
            mapping.missing.append(canonical)
        elif len(found) > 1:
            mapping.ambiguous[canonical] = found
    return mapping
