# Le Mans Ultimate telemetry MCP

A personal Python project for coaching from recorded LMU telemetry. The current package provides read-only session discovery and schema inspection. The MCP tools, HTTP server and Windows/ngrok launcher are upcoming phases in [plan.md](plan.md); the `lmu-mcp serve` and `startLeMansMCP` commands are not available yet.

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

Session IDs are relative to the fixed directory. A `discovered` status does not guarantee readability. Close the recording/game cleanly before retrying a locked or WAL-dependent file. The inspector never repairs or writes to original recordings. It describes views without executing them and retains unknown or ambiguous mappings explicitly. Time alignment and lap metrics are not implemented yet.

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
    database.py     # Read-only discovery and SQL inspection
    analysis/       # Namespace for later numerical analysis
    tools/          # Namespace for upcoming MCP tools
tests/
    test_phase1.py
```

Models and channel mapping have no MCP dependency. SQL is isolated in `database.py`; future tool definitions belong in `tools/`. Add `server.py`, telemetry/alignment modules and analysis implementations as their phases arrive. The namespace directories establish the layout and do not count as implemented tools or analysis.

The `src/` layout is installed before tests, so imports exercise the package rather than loose root-level modules. Configuration follows the [setuptools pyproject guide](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html) and the [Python packaging src-layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).

## Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
```

Tests use synthetic temporary databases and do not need LMU installed. Build creates an sdist and a wheel in ignored `dist/`. This is a local personal package; no publishing is configured. Packaging checks should install the wheel into a fresh environment and run the tests from outside the repository to catch missing files or accidental source-path dependencies.

Track completed work and test evidence in [plan.md](plan.md). Follow [AGENTS.md](AGENTS.md) for phase order and per-step tests/commits.
