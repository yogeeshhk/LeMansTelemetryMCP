# Le Mans Ultimate telemetry MCP

A personal Python project for coaching from recorded LMU telemetry. The package now provides seven read-only MCP tools for session/lap discovery, summaries, distance-aligned telemetry and lap comparison. Both stdio and Streamable HTTP have local protocol coverage. The `lmu-mcp inspect` and fixed-port `lmu-mcp serve` commands are available. The Windows/ngrok launcher and local diagnostics command are included. Public tunnel and ChatGPT validation remain open.

## Install for development

Use Python 3.13 on Windows (the verified environment). From this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If `.venv` already exists, run only the install command. Runtime, development and build dependencies are declared in `pyproject.toml`; no separate requirements files are needed. Direct dependencies are pinned; their transitive dependencies are resolved by pip.

## Inspect recorded telemetry

The production telemetry directory is fixed in `src/lmu_mcp/config.py`:

```text
D:\Steam\steamapps\common\Le Mans Ultimate\UserData\Telemetry
```

Use the Python interface after installation:

```python
from lmu_mcp.database import InspectionError, Repository

repository = Repository()
for session in repository.discover():
    print(session["session_id"], session["status"])

try:
    report = repository.inspect("Circuit de la Sarthe_R_2026-09-22T17_46_50Z.duckdb")
    print(report.channels.channels["speed"])
    print(report.channels.missing)
    print(report.warnings)
except InspectionError as error:
    print(error.code, str(error))
```

For a compact local recording check, run:

```powershell
.\.venv\Scripts\lmu-mcp.exe diagnose "Circuit de la Sarthe_R_2026-09-22T17_46_50Z.duckdb"
```

`diagnose` reports read-only database/schema availability, key channel mappings, detected lap intervals, benchmark candidates and the highest positive catalog sample rate. Missing or ambiguous channels and unavailable lap analysis are warnings; usable laps are **not** official validity decisions. It accepts only a relative session ID from the fixed telemetry directory and prints no driver metadata.

Session IDs are relative to the fixed directory. A `discovered` status does not guarantee readability. Close the recording/game cleanly before retrying a locked or WAL-dependent file. The inspector never repairs or writes to original recordings. It describes views without executing them and retains unknown or ambiguous mappings explicitly. For time alignment and lap metrics, use `lmu_mcp.service.TelemetryService` or the MCP tools described in [core-tools.md](docs/core-tools.md).

Local reports may contain numeric sample rows. Keep those reports in ignored `.runtime/` and out of Git. See [the schema findings](docs/schema-inspection.md) for producer units and timing caveats.

## Package layout

```text
pyproject.toml
README.md
src/lmu_mcp/
    __init__.py
    config.py       # Fixed telemetry root and inspection limits
    models.py       # Shared typed source/inspection contracts
    schema.py       # Channel aliases and conservative mapping
    database.py     # Read-only discovery, inspection and numeric reads
    telemetry.py    # Validated clocks and signal sampling
    alignment.py    # Bounded distance grids and crossing times
    cache.py        # Bounded revision-aware analysis cache
    diagnostics.py  # Read-only local recording report
    cli.py          # Inspect, diagnose, serve and secret rotation
    launch.py       # Owned server/ngrok lifecycle
    service.py      # Direct Python coaching API
    server.py       # MCP factory and stdio entry point
    analysis/       # Lap boundaries and compact summaries
    tools/          # Seven typed MCP tool definitions
tests/
    conftest.py
    test_phase3_mcp.py
    test_phase10_diagnostics.py
```

Models, schema mapping and numerical analysis have no MCP dependency. SQL is isolated in `database.py`; MCP definitions live in `tools/`. Advanced braking-zone and corner analysis remain in their later phases.

The `src/` layout is installed before tests, so imports exercise the package rather than loose root-level modules. Configuration follows the [setuptools pyproject guide](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html) and the [Python packaging src-layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).

## Run the current MCP server

For a local MCP client supporting stdio, use the virtual-environment Python command with arguments `-m lmu_mcp.server`:

```powershell
.\.venv\Scripts\python.exe -m lmu_mcp.server
```

The server waits for MCP protocol messages on stdin; stdout is reserved for protocol responses. This is not an interactive command shell. For local Streamable HTTP, run `.\.venv\Scripts\lmu-mcp.exe serve` from the project directory. It binds only `127.0.0.1:18765` and creates a stable private path in ignored `.runtime/private-path.txt`. The server is intentionally quiet; use an MCP client to connect. For the Windows/ngrok command `startLeMansMCP`, read [the launcher and ChatGPT setup guide](docs/windows-launcher.md). No public tunnel or ChatGPT connection has been tested yet.

## Connect an MCP client

For a local client that supports **stdio**, set its command to the absolute path of this project's `.venv\Scripts\python.exe` and its arguments to `-m lmu_mcp.server`. Start the client from any directory; stdio requires no network port. The MCP process is meant to be launched by the client, so running that command directly appears to do nothing while it waits for protocol input.

For a local client that supports **Streamable HTTP**, start `.\.venv\Scripts\lmu-mcp.exe serve` from this project directory and connect to `http://127.0.0.1:18765/<private-path>/mcp`. The private path is stored in ignored `.runtime/private-path.txt`; keep it private. For ChatGPT, use the printed **HTTPS** URL from `startLeMansMCP` and follow [the Windows launcher and ChatGPT connection guide](docs/windows-launcher.md). [OpenAI's current connection instructions](https://developers.openai.com/plugins/deploy/connect-chatgpt) describe enabling developer mode, adding an MCP server URL and reviewing discovered tools. Account/workspace availability can vary. The public route and ChatGPT interaction have not been tested in this project.

## Coaching tools

| Tool | Use |
| --- | --- |
| `list_sessions` | Find recordings by filename and page through results. |
| `get_session_info` | Check car, track, duration, available channels and recording warnings. |
| `list_channels` | Check exact signal names, producer units, frequency and missing/ambiguous mappings. |
| `list_laps` | Find recorded intervals, times, quality flags and benchmark candidates. |
| `get_lap_summary` | Review one lap's speed, controls, gear, ABS/TC and supported fuel/tyre context. |
| `compare_laps` | Locate cumulative elapsed-time changes at a coarse distance spacing. |
| `get_telemetry` | Inspect a short distance range with selected channels and shared distance samples. |

Use `list_sessions`, then `get_session_info` and `list_laps`, then summaries, a coarse `compare_laps`, and short-range `get_telemetry` calls. For example, compare two eligible laps at 20 m spacing, find where their elapsed-time delta grows, then inspect both laps over the same 200-500 m section at 1-2 m spacing. A positive A-minus-B elapsed delta means the first requested lap is slower at that distance. See [the progressive coaching workflow](docs/progressive-querying.md) and [core tool contracts](docs/core-tools.md) for arguments, units and the numerical method.

Questions to try in an MCP-enabled coaching chat:

- "Find my fastest three officially valid laps, or the fastest benchmark candidates if official validity is unavailable. Explain any exclusions."
- "Compare my fastest lap with my second-fastest lap and tell me where the major differences occur."
- "Analyse braking consistency across my five fastest laps using the summaries and available bounded telemetry; tell me what the current tools cannot establish."
- "Look closely at the braking section between 5200 m and 5450 m on two comparable laps."
- "Compare my brake release and throttle pickup through corner 7, if I provide its distance range; do not assume a named corner map."

Dedicated braking-zone and corner comparison tools are planned for Phases 12 and 13. The current seven tools can compare bounded sections, but they cannot automatically certify a braking zone or identify a named corner. Ask for observations, uncertainty and a focused practice experiment rather than a definitive driving fault.

## Limits, interpretation and privacy

Session and lap listings use pages of at most 100. Detail requests allow 1-20 channels, at most 5,000 distance samples and 20,000 estimated numeric values; comparisons use 2-10 distinct laps. The minimum spacing is 0.1 m, and responses are capped at 300 KB. If a request is rejected, use fewer channels/laps, a shorter distance range or a larger spacing. The server reads original DuckDB files with `read_only=True`, confines session IDs to the fixed root and exposes no arbitrary SQL or file-access tool.

Recordings may be unavailable while LMU is writing or a WAL file remains. Sampled signal times are inferred only when the recorded clock, sample frequencies and row counts support alignment; gaps and unsupported mappings remain missing rather than being guessed. Official lap validity is unavailable in the inspected schema (`valid: null`). `benchmark_candidate` excludes known timing, pit, impact and other quality problems, but does not prove a clean lap. Compare matching car/track conditions and consider fuel, tyres, traffic and weather before attributing time loss to driving. Source units are preserved; steering is not silently converted to degrees, and four-value tyre signals have no assumed wheel order.

The ngrok launcher exposes this **personal, read-only** MCP server through a private random URL path. Anyone with the full URL can query the recorded telemetry while the tunnel runs. Keep the URL and ngrok authtoken out of Git and logs, stop the launcher when done and run `.\.venv\Scripts\lmu-mcp.exe rotate-secret` from the project directory to change the path. Details are in [the Windows guide](docs/windows-launcher.md).

## Troubleshooting

- **No response after starting stdio:** this is expected until an MCP client sends protocol messages. Configure the client with the command and arguments above.
- **Fixed directory missing:** verify LMU is installed at the path above. The application does not search another location.
- **Recording locked, WAL present or unreadable:** close LMU cleanly, then retry. The server will not recover or modify the file.
- **Missing channel or unsupported timing:** run `.\.venv\Scripts\lmu-mcp.exe diagnose <session-id>`, inspect `list_channels` and use only verified available signals.
- **Port 18765/4040 occupied, ngrok error or ChatGPT cannot connect:** follow [the launcher troubleshooting steps](docs/windows-launcher.md). The launcher never kills another listener or silently changes ports.


## Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
```

Tests use synthetic temporary databases and do not need LMU installed. Build creates an sdist and a wheel in ignored `dist/`. This is a local personal package; no publishing is configured. Packaging checks should install the wheel into a fresh environment and run the tests from outside the repository to catch missing files or accidental source-path dependencies.

See [verification coverage and the optional real-file smoke test](docs/testing.md). Track completed work and test evidence in [plan.md](plan.md). Follow [AGENTS.md](AGENTS.md) for phase order and per-step tests/commits.
