# Progressive coaching queries

Start with a specific coaching question and stop when the evidence answers it. Server instructions and tool descriptions guide this sequence; clients still choose which tools to call.

1. Use `list_sessions` to find the intended recording, following `next_offset` when needed. Do not assume the newest recording is the intended one.
2. Read `get_session_info` for car, track, units and coverage. Use `list_channels` only when a needed signal or unit is unclear.
3. Read `list_laps`, including flags and pagination. Choose comparable `benchmark_candidate` laps. These are not officially certified valid laps. If fewer than two candidates exist, summarize the available lap and explain why comparison is unavailable.
4. Call `get_lap_summary` for both laps. Consider fuel, tyres, coverage and unavailable context before attributing differences to driving.
5. Call `compare_laps` with the coached lap first and reference second, a few channels and `resolution_m` of 20-50. Positive elapsed A-minus-B delta means the coached lap is slower.
6. Locate a section where delta increases: local loss is `delta(end) - delta(start)`. A large cumulative delta can come from an earlier section. Use finite values only; nulls and gaps are missing evidence. Coarse control-point differences can help locate a section but do not establish a cause.
7. Call `get_telemetry` on both laps over the same explicit distance range, usually 200-500 m at 1-2 m spacing. Request only channels needed for the question. Separate observations from hypotheses, then suggest a focused practice experiment.

For example, after comparing laps `[2, 1]`, a delta of 0 s at 40 m and 2 s at 60 m means lap 2 lost 2 s in that section. A delta still equal to 2 s at 80 m adds no further local loss. On this short synthetic track, query each lap with:

```json
{"session_id":"race.duckdb","lap":2,"channels":["speed"],"start_distance_m":30,"end_distance_m":70,"resolution_m":1}
```

Repeat with `lap: 1`. The protocol regression test executes discovery, both summaries, a coarse comparison, selection by local delta growth, and matching detailed queries against a synthetic recording with this known loss.

Larger `resolution_m` means fewer points. Avoid full-lap high-resolution requests, every-channel downloads and repeated refinement to minimum spacing. If a query exceeds a limit, shorten its range, reduce channels or increase spacing. If data is missing or alignment unsupported, explain the limitation rather than filling it with invented values. See [core tool contracts](core-tools.md) for numerical limits and interpolation details.

For braking questions after the coarse comparison, call `get_braking_zones` on the coached and reference laps, then `compare_braking_zones` with the same thresholds. Review unmatched/partial zones and ABS coverage before claiming a difference. For a named corner question, call `get_track_guide` after confirming the exact layout and inspect its source/calibration status. Then call `get_corners` on the reference lap and use its `corner_id` in `compare_corner` with 2-5 candidates. Automatic corner IDs are lap-local; the comparison matches by start distance within 100 m and reports unmatched laps. User manual names take priority; curated names require a unique sourced match. Unknown or approximate names do not prove a measured corner boundary. Read quality flags, ABS/TC coverage and reconstructed section-time caveats before proposing a driving experiment. This workflow has local MCP protocol coverage, not an actual ChatGPT or public ngrok integration test.
