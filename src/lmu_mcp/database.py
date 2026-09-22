"""Read-only DuckDB discovery and inspection; independent of MCP transport."""
from contextlib import contextmanager
import math
import os
from pathlib import Path

import duckdb
from .config import MAX_CATALOG_ROWS, MAX_TABLES, TELEMETRY_ROOT
from .models import Column, Inspection, Table
from .schema import map_channels


class InspectionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def inspect_connection(connection, session_id="synthetic") -> Inspection:
    """Inspect base tables only. Views are described but never selected from."""
    objects = connection.execute("""SELECT table_schema,table_name,table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema','pg_catalog')
        ORDER BY table_schema,table_name LIMIT ?""", [MAX_TABLES + 1]).fetchall()
    if len(objects) > MAX_TABLES:
        raise InspectionError("inspection_limit", "Too many tables for a bounded schema inspection.")
    tables = []
    for namespace, name, kind in objects:
        columns = tuple(Column(n, typ) for n, typ in connection.execute("""
            SELECT column_name,data_type FROM information_schema.columns
            WHERE table_schema=? AND table_name=? ORDER BY ordinal_position
        """, [namespace, name]).fetchall())
        count, samples = None, ()
        if kind == "BASE TABLE":
            qualified = identifier(namespace) + "." + identifier(name)
            count = connection.execute("SELECT count(*) FROM " + qualified).fetchone()[0]
            # Metadata contains identity/setup data. Inspect its structure, not values.
            if name != "metadata":
                # Fetch numeric signal samples only; no unbounded strings/blobs or identity fields.
                if all(c.data_type in {"BOOLEAN", "FLOAT", "DOUBLE", "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT"} for c in columns):
                    samples = tuple(tuple(v if not isinstance(v,float) or math.isfinite(v) else None for v in row)
                                    for row in connection.execute("SELECT * FROM " + qualified + " ORDER BY rowid LIMIT 2").fetchall())
        tables.append(Table(namespace, name, kind, columns, count, samples))
    catalog = {}
    warnings = []
    for table_name, name_col, expected in [
        ("channelsList", "channelName", {"channelName", "frequency", "unit"}),
        ("eventsList", "eventName", {"eventName", "unit"}),
    ]:
        table = next((t for t in tables if t.schema == "main" and t.name == table_name and t.kind == "BASE TABLE"), None)
        if table is None:
            continue
        if not expected <= {c.name for c in table.columns}:
            warnings.append(f"Malformed catalog: {table_name}")
            continue
        if table.row_count > MAX_CATALOG_ROWS:
            raise InspectionError("inspection_limit", "Channel catalog exceeds inspection limit.")
        sampled = table_name == "channelsList"
        sql = f'SELECT {identifier(name_col)},unit' + (",frequency" if sampled else "") + f' FROM {identifier(table_name)}'
        for row in connection.execute(sql).fetchall():
            name, unit = row[:2]
            if not isinstance(name,str) or (unit is not None and not isinstance(unit,str)):
                warnings.append(f"Invalid catalog entry in {table_name}")
                continue
            frequency = row[2] if sampled else None
            if frequency is not None and (not isinstance(frequency,(int,float)) or not math.isfinite(frequency) or frequency <= 0):
                warnings.append(f"Invalid sample frequency for {name}")
                frequency = None
            if name in catalog:
                raise InspectionError("ambiguous_catalog", "A signal appears multiple times in the channel catalogs.")
            catalog[name] = {"kind": "sampled" if sampled else "event", "unit": unit or None, "frequency_hz": frequency}
            if not any(t.schema=="main" and t.name==name and t.kind=="BASE TABLE" for t in tables):
                warnings.append(f"Catalog signal lacks a base table: {name}")
    channel_map = map_channels(tables, catalog)
    if all(v is None for v in channel_map.channels.values()):
        warnings.append("Unsupported or ambiguous schema: no canonical channels could be mapped.")
    return Inspection(session_id, tables, channel_map, catalog, warnings + channel_map.warnings)


class Repository:
    def __init__(self, root: Path = TELEMETRY_ROOT):
        # Dependency injection is solely for tests; production has no directory option.
        self.root = Path(root).resolve()

    def _root_check(self):
        if not self.root.is_dir():
            raise InspectionError("directory_unavailable", "The fixed LMU telemetry directory is missing or unreadable. Check the installation and folder access.")

    def resolve(self, session_id: str) -> Path:
        self._root_check()
        relative = Path(session_id)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise InspectionError("invalid_session", "Use a relative session ID returned by discovery.")
        try:
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root) or path.suffix.lower() != ".duckdb" or not path.is_file():
                raise InspectionError("invalid_session", "Session must be an existing DuckDB recording inside the fixed telemetry root.")
        except OSError as exc:
            raise InspectionError("unavailable", "Recording path cannot be accessed.") from exc
        return path

    def discover(self) -> list[dict]:
        self._root_check()
        items=[]
        def onerror(exc):
            raise InspectionError("directory_unavailable", "A telemetry directory could not be read; check folder permissions.") from exc
        for directory, subdirs, filenames in os.walk(self.root, followlinks=False, onerror=onerror):
            subdirs[:] = [d for d in subdirs if not (Path(directory)/d).is_symlink()
                          and not (Path(directory)/d).is_junction()
                          and (Path(directory)/d).resolve().is_relative_to(self.root)]
            for name in filenames:
                if Path(name).suffix.lower() != ".duckdb":
                    continue
                p=Path(directory)/name
                if not p.resolve().is_relative_to(self.root):
                    continue
                try:
                    stat=p.stat()
                    wal=Path(str(p)+".wal").exists()
                    items.append({"session_id":p.relative_to(self.root).as_posix(),"size_bytes":stat.st_size,
                                  "modified_ns":stat.st_mtime_ns,"status":"wal_present" if wal else "discovered"})
                except OSError:
                    items.append({"session_id":p.relative_to(self.root).as_posix(),"status":"unavailable"})
        return sorted(items, key=lambda item:item["session_id"])

    @contextmanager
    def open(self, session_id):
        p=self.resolve(session_id)
        if Path(str(p)+".wal").exists():
            raise InspectionError("wal_present", "Recording has a WAL file. Close the game cleanly before inspection; this server will not recover or modify it.")
        try:
            c=duckdb.connect(str(p),read_only=True,config={"enable_external_access":"false","threads":"2","memory_limit":"512MB"})
        except duckdb.Error as exc:
            raise InspectionError("database_unavailable", "Database could not be opened read-only. It may be locked, incomplete or incompatible; close the recording and retry.") from exc
        try:
            if Path(str(p)+".wal").exists():
                raise InspectionError("wal_present", "Recording became active during inspection; close the game and retry.")
            yield c
        finally:
            c.close()

    def inspect(self, session_id) -> Inspection:
        try:
            with self.open(session_id) as c:
                return inspect_connection(c,session_id)
        except duckdb.Error as exc:
            raise InspectionError("inspection_failed", "Database opened but its schema could not be inspected safely.") from exc


class SignalReader:
    """Bounded numeric reads through inspected base-table source references."""
    def __init__(self, connection, inspection):
        self.connection = connection
        self.inspection = inspection
        self.loaded_rows = 0

    def values(self, source, columns=None):
        import numpy as np
        from .config import MAX_SOURCE_SAMPLES, MAX_TOTAL_SOURCE_SAMPLES
        table = next((t for t in self.inspection.tables
                      if (t.schema, t.name, t.kind) == (source.schema, source.table, "BASE TABLE")), None)
        columns = tuple(columns or source.value_columns)
        if table is None or not set(columns) <= {c.name for c in table.columns}:
            raise InspectionError("invalid_source", "Source must refer to inspected base-table columns.")
        count = table.row_count
        if count > MAX_SOURCE_SAMPLES or self.loaded_rows + count > MAX_TOTAL_SOURCE_SAMPLES:
            raise InspectionError("source_limit", "Recording exceeds the per-request source budget; use a shorter recording.")
        self.loaded_rows += count
        qualified = identifier(source.schema) + "." + identifier(source.table)
        sql = "SELECT " + ",".join(identifier(c) for c in columns) + " FROM " + qualified + " ORDER BY rowid LIMIT ?"
        result = self.connection.execute(sql, [MAX_SOURCE_SAMPLES + 1]).fetchnumpy()
        arrays = []
        for name in columns:
            value = np.ma.asarray(result[name], dtype=float).filled(np.nan)
            arrays.append(value)
        return np.column_stack(arrays)

    def metadata(self):
        allowed = {"Version", "RecordingTime", "SessionTime", "SessionType", "TrackName", "TrackLayout", "WeatherConditions", "CarName", "CarClass"}
        table = next((t for t in self.inspection.tables if (t.schema,t.name,t.kind)==("main","metadata","BASE TABLE")),None)
        if table is None or not {"key","value"} <= {c.name for c in table.columns}:
            return {}
        rows = self.connection.execute("SELECT key, left(value, 256) FROM metadata WHERE key IN (SELECT unnest(?)) LIMIT 20", [sorted(allowed)]).fetchall()
        return dict(rows)

    def extrema(self, source):
        # Validate the source without reading its complete values.
        table = next((t for t in self.inspection.tables if (t.schema,t.name,t.kind)==(source.schema,source.table,"BASE TABLE")),None)
        if table is None or not set(source.value_columns) <= {c.name for c in table.columns}:
            raise InspectionError("invalid_source", "Unknown source.")
        fields = []
        for col in source.value_columns:
            fields += ["min("+identifier(col)+")", "max("+identifier(col)+")"]
        row = self.connection.execute("SELECT "+",".join(fields)+" FROM "+identifier(source.schema)+"."+identifier(source.table)).fetchone()
        return {col: {"min":row[2*i],"max":row[2*i+1]} for i,col in enumerate(source.value_columns)}
