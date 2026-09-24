# Verification coverage

The default suite uses temporary synthetic DuckDB recordings and does not require Le Mans Ultimate. Run it with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite checks schema aliases, unknown or missing channels, validity/partial-lap flags and resets, sample-rate alignment, missing values, interpolation, discrete holds, exact synthetic lap comparisons, paging, explicit truncation, request and response limits, path confinement, unavailable/WAL files, cache invalidation, and unchanged read-only originals. `tests/test_phase3_mcp.py` uses real MCP clients to initialize, list tools, call every tool, reject invalid requests and validate both stdio and Streamable HTTP. A health endpoint alone is not counted as an MCP protocol test.

The file-symlink escape check skips on Windows accounts without symlink creation rights. The Windows junction escape test runs separately and verifies the same path-confinement rule. `tests/test_phase8_cases.py` checks the currently implemented basic brake-application count, including a brief tap, two continuous subpeaks and an application active at lap start. Braking-zone detection and position matching have synthetic core and service tests in `tests/test_phase12_braking_core.py` and `tests/test_phase12_service.py`; corner detector, manual-definition and service cases are in `tests/test_phase13_detector.py`, `tests/test_phase13_manual.py` and `tests/test_phase13_service.py`. Launcher startup, occupied-port, readiness and child cleanup have synthetic regression coverage in `tests/test_phase9_launch.py`. `tests/test_phase10_diagnostics.py` checks read-only diagnostics, missing channels/laps, WAL/path errors and sanitized query failures. Phase 14 adds synthetic pack-loader, calibration-report and sourced-guide checks. Phase 15 checks the La Sarthe pack order, exact layout, shifted/missing associations, source-revision cache invalidation and local HTTP guide response. The MCP protocol suite now exercises all thirteen tools on stdio and HTTP, including known synthetic braking/corner differences, unknown corners and invalid thresholds. The public-tunnel and ChatGPT gates remain open.

An optional smoke test reads the supplied private recording at the fixed telemetry path, exercises discovery/summary and a short telemetry query twice, then checks SHA-256, size, modification time and WAL absence. It never writes the source or prints telemetry values. Run it only when LMU is closed cleanly:

```powershell
$env:LMU_RUN_REAL_SMOKE = '1'
try {
    .\.venv\Scripts\python.exe -m pytest tests/test_phase8_real_smoke.py -q
} finally {
    Remove-Item Env:LMU_RUN_REAL_SMOKE -ErrorAction SilentlyContinue
}
```

Public ngrok and actual ChatGPT tests have not run; those belong to Phase 9 and require the tunnel and user setup. Test results are recorded in [plan.md](../plan.md).


Phase 16 tests (`tests/test_phase16_coaching.py`, `tests/test_phase16_pack.py`, `tests/test_phase16_integration.py`) cover bounded evidence/applicability notes, guide independence from lap analysis, exact Spa identity, complete guide topics, split/merged association rejection, source revisions, synthetic rain/missing speed/reversal cases, and actual stdio/HTTP initialization, discovery, paged guide calls, subsequent Campus comparison and invalid requests. Synthetic intervals shifted to the Campus region test association without reproducing a private lap. These local tests do not certify wet braking targets, optimal setup, public ngrok access or actual ChatGPT response quality.

Phase 17 tests (`tests/test_phase17_pack.py`, `tests/test_phase17_integration.py`) cover exact Monza identity, unknown variants, an all-approximate ordered pack, unique future association, explicit calibration replacement, the present distance-reversal failure and actual stdio/HTTP guide calls. Synthetic intervals shifted near Curva di Lesmo 1 test approximate status propagation without reproducing private telemetry. The real-file read-only limitation is checked separately; these tests do not claim calibrated Monza corner metrics or universal setup targets.

Phase 18 tests (`tests/test_phase18_excursions.py`, `tests/test_phase18_service.py`, `tests/test_phase18_mcp.py`) cover sustained repeated events on both signs, short noise, missing samples and gaps, reversed distance, missing/ambiguous semantics, partial and flagged laps, exact car/layout history filtering, unique sourced-feature association, pagination/cost limits and actual stdio/HTTP calls for both scopes and errors. Surface codes and GPS remain deliberately non-triggering. Real-file validation is reported separately and does not certify official track limits.
