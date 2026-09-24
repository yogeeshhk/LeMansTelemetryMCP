# Le Mans Ultimate telemetry MCP

A personal Python project for coaching from recorded LMU telemetry. The package now provides seven read-only MCP tools for session/lap discovery, summaries, distance-aligned telemetry and lap comparison. Both stdio and Streamable HTTP have local protocol coverage. The `lmu-mcp inspect` and fixed-port `lmu-mcp serve` commands are available. The Windows/ngrok launcher is included; public tunnel and ChatGPT validation remain open.

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

`diagnose` reports read-only database/schema availability, key channel mappings, detected lap intervals, benchmark candidates and the highest verified catalog sample rate. Missing or ambiguous channels and unavailable lap analysis are warnings; usable laps are **not** official validity decisions. It accepts only a relative session ID from the fixed telemetry directory and prints no driver metadata.

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
    service.py      # Direct Python coaching API
    server.py       # MCP factory and stdio entry point
    analysis/       # Lap boundaries and compact summaries
    tools/          # Seven typed MCP tool definitions
tests/
    test_phase1.py
```

Models, schema mapping and numerical analysis have no MCP dependency. SQL is isolated in `database.py`; MCP definitions live in `tools/`. Advanced braking-zone and corner analysis remain in their later phases.

The `src/` layout is installed before tests, so imports exercise the package rather than loose root-level modules. Configuration follows the [setuptools pyproject guide](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html) and the [Python packaging src-layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).

## Run the current MCP server

For a local MCP client supporting stdio, use the virtual-environment Python command with arguments `-m lmu_mcp.server`:

```powershell
.\.venv\Scripts\python.exe -m lmu_mcp.server
```

The server waits for MCP protocol messages on stdin; stdout is reserved for protocol responses. This is not an interactive command shell. For local Streamable HTTP, run `.\.venv\Scripts\lmu-mcp.exe serve` from the project directory. It binds only `127.0.0.1:18765` and creates a stable private path in ignored `.runtime/private-path.txt`. The server is intentionally quiet; use an MCP client to connect. For the Windows/ngrok command `startLeMansMCP`, read [the launcher and ChatGPT setup guide](docs/windows-launcher.md). No public tunnel or ChatGPT connection has been tested yet.

See [the progressive coaching workflow](docs/progressive-querying.md) for the recommended query sequence. See [core tool contracts and methodology](docs/core-tools.md) for examples, query limits and interpretation of lap deltas.

## Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
```

Tests use synthetic temporary databases and do not need LMU installed. Build creates an sdist and a wheel in ignored `dist/`. This is a local personal package; no publishing is configured. Packaging checks should install the wheel into a fresh environment and run the tests from outside the repository to catch missing files or accidental source-path dependencies.

See [verification coverage and the optional real-file smoke test](docs/testing.md). Track completed work and test evidence in [plan.md](plan.md). Follow [AGENTS.md](AGENTS.md) for phase order and per-step tests/commits.
