# Sourced track knowledge packs

Place versioned `.json` files here. These are separate from user manual corner overrides in the parent directory. Packs match exact recorded `TrackName` and `TrackLayout`; a pack never changes original telemetry or repairs a lap path.

Each pack has `version: 1`, `track`, `layout`, `status` (`calibrated` or `approximate`), 1-32 `sources`, and 1-128 ordered `features`. A source has a unique `id`, short `title`, HTTPS `url` and ISO `retrieved` date. Every feature cites 1-5 source IDs and has a unique `feature_id`, `name`, `kind` (`corner`, `complex`, `straight`, `sector`, `landmark`), integer `order`, and `status` (`calibrated`, `approximate`, `unmatched`). Optional `character` is a sourced short note, not a setup recommendation.

A ranged feature needs `start_distance_m`, `end_distance_m`, `uncertainty_m`, and `distance_method`; unmatched features have no distance fields. Calibrated features require ranges. Corner-to-corner ranges cannot overlap; sectors, straights and landmarks may overlap corners. Each file is limited to 64 KiB and this directory to 32 files. A pack source must be reviewed against the specific game layout and telemetry before being marked calibrated. No live web fetch occurs during MCP requests.

Example synthetic pack:

```json
{
  "version": 1,
  "track": "Synthetic",
  "layout": "Test",
  "status": "calibrated",
  "sources": [{"id": "official", "title": "Example circuit map", "url": "https://example.org/map", "retrieved": "2026-09-24"}],
  "features": [{"feature_id": "turn-one", "name": "Turn One", "kind": "corner", "order": 1, "status": "calibrated", "start_distance_m": 25, "end_distance_m": 65, "uncertainty_m": 5, "distance_method": "Reviewed against two synthetic laps", "source_ids": ["official"]}]
}
```

To review candidate distance associations before marking a pack calibrated, run the local read-only report from the project directory:

```powershell
.\.venv\Scripts\lmu-mcp.exe calibration-report '<relative-session-id>' --max-laps 5
```

The command prints bounded JSON with complete-lap turn ranges, optional rounded GPS points, candidate feature IDs and unsupported lap codes. It omits driver and setup metadata. Redirect it into ignored `.runtime/` if a local review artifact is useful; do not commit the output or treat a candidate association as verified without checking the source map and multiple laps.
