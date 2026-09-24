# Verification coverage

The default suite uses temporary synthetic DuckDB recordings and does not require Le Mans Ultimate. Run it with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite checks schema aliases, unknown or missing channels, validity/partial-lap flags and resets, sample-rate alignment, missing values, interpolation, discrete holds, exact synthetic lap comparisons, paging, explicit truncation, request and response limits, path confinement, unavailable/WAL files, cache invalidation, and unchanged read-only originals. `tests/test_phase3_mcp.py` uses real MCP clients to initialize, list tools, call every tool, reject invalid requests and validate both stdio and Streamable HTTP. A health endpoint alone is not counted as an MCP protocol test.

The file-symlink escape check skips on Windows accounts without symlink creation rights. The Windows junction escape test runs separately and verifies the same path-confinement rule. `tests/test_phase8_cases.py` checks the currently implemented basic brake-application count, including a brief tap, two continuous subpeaks and an application active at lap start. Braking-zone and corner detection do not exist in the core yet; their zone/corner-specific tests belong to Phases 12 and 13. Launcher startup, occupied-port, readiness and child cleanup tests belong to Phase 9 when the launcher exists. These gates remain open.

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
