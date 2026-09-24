# Optional manual corner definitions

Place at most 32 UTF-8 `.json` files in this directory. A definition overrides automatic ranges only when `track` and `layout` exactly equal the recording's `TrackName` and `TrackLayout` metadata. Use `get_session_info` to inspect those names. This is an editable-install project directory; package builds include any definition JSON files present when built.

Example file `example.json` (replace the names and measured distance bounds for your own layout):

```json
{
  "track": "Example Track",
  "layout": "Example Layout",
  "corners": [
    {"corner_id": 1, "name": "Turn 1", "start_distance_m": 400.0, "end_distance_m": 570.0, "apex_distance_m": 485.0},
    {"corner_id": 2, "name": "Turn 2", "start_distance_m": 680.0, "end_distance_m": 820.0}
  ]
}
```

Ranges must be nonoverlapping, at most 2,000 m each and within 0-200,000 m. IDs must be unique positive integers. An omitted apex is estimated from the minimum recorded speed. No named corners are provided by default; do not guess official names from telemetry. The server reads these files but never writes them.
