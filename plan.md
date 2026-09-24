# Le Mans Ultimate Telemetry MCP Server Plan

Build a reliable personal-use Python MCP server for analysing Le Mans Ultimate telemetry stored in DuckDB.
The primary consumer will be an AI driving coach such as ChatGPT. The AI should never need to load an entire telemetry database. Instead, it should progressively query session → laps → sectors/corners → high-resolution telemetry.

## Objective

Create a read-only MCP server that:

- discovers LMU .duckdb telemetry files
- understands their schema automatically
- exposes useful racing-analysis tools
- prevents excessively large responses
- aligns telemetry by lap distance
- supports comparing laps
- detects braking zones and major corner events
- works with different LMU telemetry schemas where possible
- keeps the original DuckDB untouched
- is easy to run locally
- supports stdio and Streamable HTTP for ChatGPT access through ngrok in Milestone 1

Use Python.

Prefer:

- duckdb
- mcp / FastMCP from the official MCP Python SDK
- pydantic
- numpy
- pandas only where useful
- pytest

Do not build a frontend.

## Scope, evidence and implementation gates

This is a single-owner personal project. Do not build multi-user support, accounts, roles, tenancy, per-user storage or an OAuth service. Keep the existing private-URL ngrok access model and basic read-only/path safeguards.

The telemetry directory is fixed:

```text
D:\Steam\steamapps\common\Le Mans Ultimate\UserData\Telemetry
```

Define this path once as an application constant. Do not add a directory picker, a telemetry-directory CLI option or an environment override. Tests may inject temporary roots internally; this is not a user-facing configuration feature.

`plan.md` is the sole implementation plan. Follow every phase in the order below; the advanced braking and corner phases follow the complete core milestone. Requirements for safety, bounded output and testing apply from the first change, even before their dedicated phase is completed.

Scope is coaching from recorded telemetry, not a live shared-memory plugin. Preserve original DuckDB files. Do not expose arbitrary SQL, database writes, arbitrary filesystem reads or a frontend. Provide fuel/tyre statistics and compact coaching context through the summary/channel tools where supported; avoid duplicating tools merely to give them coaching-oriented names.

Observed caveats from the supplied race recording must become adapter checks and regression cases, not universal assumptions about every LMU file:

- Signals are split between sampled tables, timestamped event tables and catalogs containing units/frequencies. Most sampled tables lack explicit timestamps. Validate frequency ratios and sample counts against the recording clock; report inferred alignment, and refuse unsupported reconstruction rather than inventing precision.
- The recording contains pre-race time, an unclosed post-finish tail, a clock gap, an impact event and a final lap-completion event with zero reported lap time. Separate recorded timing from inferred boundary duration; flag incomplete or suspect laps.
- Official lap validity is unavailable in this schema. Return `valid: null`; expose benchmark eligibility and exclusion reasons separately. Do not describe a candidate as a certified clean lap.
- Units must come from verified metadata or explicit conversions. Ground Speed is recorded in km/h in this file. Do not relabel steering as degrees or guess wheel order from component indices.
- Do not invent named corners, race-weekend groupings or missing metadata. Automatic corners are approximate distance ranges; named ranges require supplied track definitions.
- Compare compatible track layouts and cars. Report fuel, tyre, weather, traffic and data-quality limitations; measured differences alone do not establish a driving error.

| Milestone | Required phases | Exit gate |
| --- | --- | --- |
| 1: working core and remote access | 1-11, sequentially | Real-file schema report, bounded core tools, tests, CLI, diagnostics, README, HTTP handshake and Windows/ngrok launcher validation. |
| 2: braking analysis | 12 | Tested zone detection and position-based zone comparison, documented thresholds and limitations. |
| 3: corners and advanced coaching | 13 | Tested automatic/manual corner ranges and corner comparison, integrated progressive coaching workflow. |

Do not start the next milestone until the current exit gate passes. Do not silently omit a phase, replace its requirements with placeholders, or call a partially tested milestone complete. If external access blocks a check, record the blocker and keep that gate open. Only tested, committed implementation counts toward phase completion.

For each small implementation step: make the change, run relevant tests/checks, update this plan's progress log with evidence, and create a focused Git commit before starting the next step. Run the complete applicable test suite at milestone boundaries. Documentation-only steps require document/link/consistency checks rather than unrelated application tests.

### Progress log

- Phase 11 follow-up documentation fix: a fresh PowerShell terminal reported `startLemansMCP` as unknown because the profile function had not been loaded; this account's PowerShell profile file does not yet exist. Verified that dot-sourcing the checked-in function makes the exact case-insensitive command resolve without starting ngrok. Added an immediate-use dot-source step to the Windows guide, separate from the existing one-time profile installation. Guide links/fences/command check and Git diff check passed. No live tunnel was started.

- Phase 11 documentation complete: expanded README with exact stdio/HTTP client setup, all seven current tools, progressive coaching workflow, request limits, recording/timing/validity/comparison caveats, read-only and private-URL security, troubleshooting, and the five requested coaching questions. Added a one-time PowerShell profile-install command to the Windows guide and corrected stale launcher/testing text in supporting docs. Documentation-only checks passed: six Markdown files have balanced fences and valid local links; README tool names match current definitions, all required topics/questions and runnable project commands are present; profile function parses and loads; `git diff --check` passed. Application tests were not rerun because this step changes prose only. Public ngrok and actual ChatGPT checks remain unexecuted by the user's choice, so Milestone 1 remains open and Phase 12 is gated.

- Phase 10 complete at the user's direction while the Phase 9 public integration gate remains open: added `lmu-mcp diagnose <relative-session-id>` and a direct-Python read-only diagnostic report. It shows database/schema readability, mapped key channels, detected lap intervals, benchmark candidates rather than official validity, highest positive finite catalog sample rate, and actionable missing/ambiguous-channel or lap-analysis warnings. Synthetic regressions cover counts, missing channels/laps, WAL and path rejection, and sanitized DuckDB errors. Focused tests: 9 passed before final late-query handling; complete `python -m pytest -q`: 88 passed, 2 skipped. The supplied recording passed a local CLI smoke check with original size, mtime and SHA-256 unchanged. Wheel contains the new module; README links, fences, command and Git diff check passed. The user explicitly chose to skip the live ngrok test and begin Phase 10. Public ngrok and ChatGPT validation remain untested, so Milestone 1 is still open.

- Phase 9, step 2 implementation complete; public integration gate open: added `startLeMansMCP.ps1`, copyable profile function, ngrok Host rewrite policy, and Python launcher. It validates the fixed directory, ngrok installation/config syntax and ports; completes a real local MCP handshake before starting ngrok; discovers the HTTPS origin via the local agent API; monitors and cleans only its owned child processes. Added `docs/windows-launcher.md` for installation, ChatGPT setup, private-path rotation and troubleshooting. Focused launcher/CLI/MCP tests: 15 passed; full `python -m pytest -q`: 82 passed, 2 skipped; local preflight passed; PowerShell parser/profile load passed; wheel/sdist builds passed and sdist contents checked; Markdown links/fences and diff check passed. No public tunnel or ChatGPT connection was exercised. An attempted live ngrok test was rejected by automatic approval review because it would expose the live endpoint and send recording metadata through ngrok; public validation therefore remains an open Phase 9 gate pending explicit authorization. At that point, Phase 10 had not begun.

- Phase 9, step 1 complete: added installed `lmu-mcp inspect`, `lmu-mcp serve` and `rotate-secret` commands; the HTTP server binds only `127.0.0.1:18765` with an occupied-port error, stable ignored random MCP path, and explicit Host/Origin checks. Direct dependencies updated for uvicorn. Actual local fixed-port CLI smoke initialized MCP, listed seven tools and discovered 73 sessions; the owned test process was stopped. `python -m pytest tests/test_phase9_cli.py tests/test_phase3_mcp.py -q`: 9 passed, covering private path, wrong path, Host/Origin rejection and occupied port. Ngrok launcher/readiness/public tests remain Phase 9 work.

- Phase 8 core testing complete, step 2: added opt-in `tests/test_phase8_real_smoke.py` and `docs/testing.md`, linked from README. Full `python -m pytest -q`: 72 passed, 2 skipped (real test intentionally opt-in; file symlink creation unavailable on this Windows account). With `LMU_RUN_REAL_SMOKE=1`, the supplied-race smoke test passed 1/1 and confirmed SHA-256/size/mtime/WAL absence unchanged. The full suite includes real stdio and Streamable HTTP MCP initialization, tool discovery, successful/invalid calls and errors. Braking-zone/corner-specific checks remain for Phases 12/13; launcher readiness/port/process checks remain for Phase 9. Public ngrok/ChatGPT tests have not run. Phase 9 is next; Milestone 1 remains open.

- Phase 8, step 1 complete: added synthetic checks for 10 Hz/5 Hz interpolation and discrete gear hold, null propagation after a missing sample, basic brake application/tap thresholds, session pagination and explicit control-onset truncation. `python -m pytest tests/test_phase8_cases.py -q`: 4 passed, 1 skipped because this Windows account cannot create file symlinks; the existing junction escape test still passes. Advanced braking-zone/corner scenarios remain for their implementation in Phases 12/13. Optional real-file smoke and milestone verification are next.

- Phase 7 complete, step 2: cached validated distance paths and exact aligned lap arrays by recording revision, lap, channels, bounds, spacing and source-budget settings. Repeated calls reuse internal arrays; returned JSON is an independent copy. Synthetic tests verify cache hits, spacing-specific entries, changed speed values after a file edit, byte-budget rejection and tightened source-budget rejection. `python -m pytest tests/test_phase7_cache.py tests/test_phase3_service.py -q`: 27 passed; full `python -m pytest -q`: 68 passed. Read-only supplied-race smoke returned the same 101 points on a repeated request with four cache entries and unchanged SHA-256/size/mtime. Updated core tool/README docs. Braking-zone and corner analyses do not exist until Phases 12/13; their derived entries will use this cache when implemented. Phase 8 is next; Milestone 1 remains open.

- Phase 7, step 1 complete: added a thread-safe 64-entry/64 MiB process LRU for inspection/channel mapping and lap boundaries. Each request still opens DuckDB read-only and checks the recording revision; changed mtime/size/file identity evicts prior entries. WAL/open failures are never cached. Three new synthetic cache tests verify reuse, changed-file recomputation, WAL retry, LRU bounds and stale-put rejection. `python -m pytest tests/test_phase7_cache.py -q`: 3 passed; affected service/safety suite: 25 passed. Distance alignment remains for this phase.

- Phase 6 complete, step 2: MCP tool calls now return validated structured content plus compact equivalent JSON text, avoiding SDK-indented array duplication while preserving client compatibility and the 300 KB envelope check. Actual stdio/HTTP client suite: `python -m pytest tests/test_phase3_mcp.py -q`: 5 passed with text/structured parity assertions. A 201-point section of the supplied race measured 7,166 compact text bytes versus 13,673 indented bytes (47.6% less text); only lengths were printed. Full `python -m pytest -q`: 63 passed. Phase 7 is next; Milestone 1 remains open.

- Phase 6, step 1 complete: telemetry remains column-oriented, with wire-only precision by verified unit/field (km/h 0.1, percentage controls 0.001, seconds 0.001, distance at least 0.1 m and finer when grid spacing requires it). Internal arrays stay unrounded and non-finite values remain null. Synthetic checks cover a 0.125 m grid, speed/brake samples, comparison deltas and summary speed; `python -m pytest tests/test_phase6_representation.py tests/test_phase3_service.py -q`: 23 passed. Precision policy documented in `docs/core-tools.md`. Compact MCP text serialization remains for this phase.

- Phase 5 complete, step 3: explicit telemetry/comparison bounds now preflight channels, distance, spacing, lap count and projected array size before opening DuckDB; omitted end bounds are checked after lap coverage is known. Query-limit errors advise fewer channels/laps, a shorter section or larger metre spacing. Synthetic `NeverOpen` regression confirms oversized requests fail before database access. `python -m pytest tests/test_phase5_safety.py tests/test_phase3_service.py tests/test_phase3_mcp.py -q`: 30 passed; full `python -m pytest -q`: 62 passed. Real-file smoke: supplied race reports 104 tables and 5 completed intervals, with SHA-256/size/mtime unchanged. Bounded discovery found 73 recordings, 2 with WAL files. Updated `docs/core-tools.md` with connection and discovery limits. Phase 6 is next; Milestone 1 remains open.

- Phase 5, step 2 complete: recursive discovery now scans lazily with a 20,000-entry ceiling and raises `discovery_limit` instead of returning a partial list. Junctions/symlinks still cannot escape the root. `python -m pytest tests/test_phase5_safety.py tests/test_phase1.py -q`: 24 passed after the initial scan change; the final file-type guard was then checked by the same focused suite. Query preflight and actionable budget errors remain.

- Phase 5, step 1 complete: DuckDB now explicitly disables external access, extension auto-loading/installation and unsigned extensions on original read-only connections. Synthetic regression confirms all four settings are false, writes are refused and database bytes remain unchanged. `python -m pytest tests/test_phase5_safety.py tests/test_phase1.py -q`: 23 passed. Discovery and query-budget limits remain for Phase 5.

- Phase 4 complete: strengthened server instructions and all seven tool descriptions for discovery, both lap summaries, coarse comparison, local delta growth and bounded detail on both laps. Added `docs/progressive-querying.md` and a linked README workflow. Actual MCP synthetic regression locates a known 2 s loss at 40-60 m and confirms it with matching 30-70 m queries; `python -m pytest tests/test_phase3_mcp.py -q`: 5 passed, including stdio/HTTP protocol and error coverage. Markdown links/fences and staged whitespace checks passed. Future corner/braking tools remain gated by Phases 12/13. No public tunnel or actual ChatGPT behavior test was performed. Phase 5 is next; Milestone 1 remains open.

- Phase 3 complete, step 3: registered all seven typed, read-only MCP tools with structured results, bounded worker execution and sanitized errors. Verified actual stdio and Streamable HTTP initialization/discovery/calls, schema validation, path rejection, query/envelope limits and Host validation. Final `python -m pytest -q`: 58 passed; `python -m build` and `pip check` passed; distribution contents checked (including shared test fixtures). All seven tools passed through the production stdio entry point against the supplied race; original SHA-256/size/mtime unchanged, largest tested MCP response 210510 bytes. Added `docs/core-tools.md` and updated README. Public ngrok/ChatGPT integration remains untested and belongs to Phase 9; Phase 4 is next, Milestone 1 remains open.
- Phase 3, step 2 complete: implemented the direct seven-method API, bounded distance grids, continuous interpolation/discrete holds, time-weighted summaries and elapsed-time lap deltas with coarse control-onset differences. Fixed an integer-grid dtype defect exposed by tests. All 20 new service tests pass; the prior 32 tests passed in the combined run before that localized fix. Real recording: 201-point section query and 681-point lap comparison pass, reproducing the 1.5378 s reported lap 2/4 delta. MCP registration/integration is next; Phase 3 remains open.
- Phase 3, step 1 complete: added bounded numeric signal reads, explicit clock-stride validation, discrete event handling and lap completion/partial-interval identification. `python -m pytest -q`: 32 passed. Read-only supplied-race smoke test reproduces four positive reported lap times, the zero-time completion, impact flag and incomplete tail. NumPy/MCP dependencies pinned; public tools and distance analysis remain in progress.
- Phase 2 complete: moved the tested inspector into `src/lmu_mcp/database.py`, split source contracts into `models.py`, centralized the fixed path/limits in `config.py`, and retained mapping in `schema.py`. Added analysis/tools namespaces, `pyproject.toml`, `MANIFEST.in`, installation/build README and build-artifact ignores. Editable install and `python -m build` passed; 22 tests passed against both editable and fresh wheel installs (wheel tests ran outside the repository). Archive checks confirmed the expected modules/docs and no private runtime/database files; fresh-environment `pip check` passed. Phase 3 is next; Milestone 1 remains open.
- Repository cleanup: removed unused, untracked `telemetry.py`, `requirements.txt` and `requirements-dev.txt`; updated stale documentation. Phase 1 regression suite: 22 passed. Package/dependency setup remains scheduled for Phase 2.
- Phase 1 complete, step 2: added standalone `inspection.py` and `schema.py` with conservative aliases, missing/ambiguous mappings, read-only discovery/inspection and explicit unavailable/WAL errors. `python -m pytest tests/test_phase1.py -q`: 22 passed. Real-file smoke test: 57 inspected, two WAL recordings skipped, one schema variant; SHA-256/size/mtime unchanged for all 61 database/WAL files. See `docs/schema-inspection.md`. Phase 2 is next; Milestone 1 remains open.
- Phase 1, step 1 complete: inspected all 59 recordings (57 readable with one schema signature, two WAL files skipped); saved the 104-table inventory and proposed adaptations in `docs/schema-inspection.md`. Sample rows remain in ignored `.runtime/phase1-samples.json`. Verified supplied-file SHA-256 unchanged and inventory/catalog counts. Schema abstraction and its tests remain pending.
- Personal-use scope update: fixed the telemetry root, removed directory overrides and multi-user architecture requirements, retained internal test-root injection and existing read-only/ngrok safeguards. Documentation checks passed for consistent paths and commands, all 13 phase gates, balanced code fences and required test/commit rules.
- Planning: merged the prior scope and deployment caveats; reordered all 13 phases to make the milestone gates executable. No implementation phase is declared complete by this planning update.
- Planning validation: Python assertions passed for all 13 sequential phases, retained deployment/data caveats, milestone consistency, required agent rules, balanced code fences and removal of redundant plans. Application tests are not applicable to this documentation-only step. Initialized local Git for the required per-step commits; existing prototype files remain outside this documentation commit.

## Phase 1 — Inspect the telemetry

Before implementing assumptions about the LMU schema:
Use the fixed telemetry directory above. If it is missing or unreadable, return an actionable error; do not search alternative installations or silently fall back to another directory.
Discover `.duckdb` files recursively on each listing, including newly saved recordings and nested directories. Preserve relative session identifiers; do not invent a race-weekend identifier. Resolve paths within the fixed telemetry root, including Windows junctions and symlinks.
Open databases in `read_only=True`. Report locked, incomplete, unsupported or WAL-recovery-dependent files clearly; never recover or modify an original database. One unavailable session must not prevent listing other recordings. Save schema findings and data-quality evidence before implementing schema-specific logic.

Inspect:

- tables
- views
- columns
- types
- row counts
- sample rows

Identify likely telemetry channels including:

- timestamp/time
- lap number
- lap distance
- ground speed
- throttle
- brake
- steering
- gear
- RPM
- longitudinal acceleration
- lateral acceleration
- yaw rate
- wheel speeds
- ABS
- TC
- brake bias
- tyre data

Produce a schema abstraction rather than hardcoding one exact LMU schema.
Create something like:

```python
@dataclass
class ChannelMap:
    timestamp: str | None
    lap_number: str | None
    lap_distance: str | None
    speed: str | None
    throttle: str | None
    brake: str | None
    steering: str | None
    gear: str | None
    rpm: str | None
    ...
```

Support channel aliases so schema changes do not immediately break the application.

## Phase 2 — Project structure

Use a structure approximately like:

```text
lmu-mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── lmu_mcp/
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       ├── database.py
│       ├── schema.py
│       ├── models.py
│       ├── telemetry.py
│       ├── alignment.py
│       ├── analysis/
│       │   ├── laps.py
│       │   ├── braking.py
│       │   ├── corners.py
│       │   └── comparison.py
│       └── tools/
│           ├── sessions.py
│           ├── laps.py
│           ├── telemetry.py
│           └── analysis.py
└── tests/
```

Keep SQL/database access separate from MCP tool definitions.

The tree is the target architecture across phases. Phase 2 creates the installable package, shared models/configuration, existing database/schema modules and analysis/tools namespaces. Add executable server, telemetry/alignment and analysis modules when their implementation phases arrive; empty namespaces are scaffolding, not completed features. Verify editable installation, build a wheel from the source archive, and run existing tests against a fresh wheel installation outside the source checkout. Keep build products and environment files ignored.

## Phase 3 — MCP tools

Implement the following tools.

### `list_sessions`

Return available telemetry recordings.
Return compact metadata:

```json
{
  "sessions": [
    {
      "session_id": "...",
      "filename": "...",
      "modified_at": "...",
      "size_bytes": 123
    }
  ]
}
```

Never expose arbitrary filesystem paths unless necessary.

### `get_session_info`

Input:

```json
{
  "session_id": "..."
}
```

Return whatever metadata is available:

- car
- track
- session type
- start time
- number of laps
- available channels
- approximate telemetry sample rates
- database tables
- session duration

Missing metadata should be null, not guessed.

### `list_channels`

Input:

```json
{
  "session_id": "..."
}
```

Return:

- canonical channel name
- source column
- units if known
- sample count
- approximate frequency
- min/max where inexpensive

Example:

```json
{
  "channels": [
    {
      "name": "speed",
      "source": "Ground Speed",
      "unit": "km/h",
      "frequency_hz": 100
    }
  ]
}
```

### `list_laps`

Input:

```json
{
  "session_id": "..."
}
```

Return one compact record per lap:

```json
{
  "lap": 12,
  "lap_time_s": 206.991,
  "valid": null,
  "max_speed_kph": 312.4,
  "sample_count": 20578
}
```

If LMU does not explicitly mark validity, expose validity as null.
Do not infer invalidity without evidence.

### `get_lap_summary`

Input:

```json
{
  "session_id": "...",
  "lap": 12
}
```

Return useful coaching metrics such as:

- lap time
- maximum speed
- minimum speed
- average speed
- percentage throttle
- percentage braking
- percentage coasting
- number of braking events
- number of gear changes
- ABS activation count/time
- TC activation count/time
- steering correction metrics if practical

Do not return raw telemetry here.

### `get_telemetry`

Inputs:

```json
{
  "session_id": "...",
  "lap": 12,
  "channels": [
    "speed",
    "brake",
    "throttle",
    "steering",
    "gear"
  ],
  "start_distance_m": 3000,
  "end_distance_m": 3400,
  "resolution_m": 1.0
}
```

Requirements:

- align samples to lap distance
- interpolate continuous channels
- use nearest/forward appropriate behaviour for discrete channels
- return data ordered by distance
- return units
- indicate interpolation method
- never silently return millions of rows

Response:

```json
{
  "lap": 12,
  "start_distance_m": 3000,
  "end_distance_m": 3400,
  "resolution_m": 1,
  "channels": {
    "speed_kph": [...],
    "brake": [...],
    "throttle": [...],
    "steering": [...],
    "gear": [...]
  },
  "distance_m": [...]
}
```

Prefer column-oriented arrays over thousands of repeated JSON objects because they are much more token-efficient.

### `compare_laps`

Inputs:

```json
{
  "session_id": "...",
  "laps": [7, 11],
  "channels": [
    "speed",
    "brake",
    "throttle",
    "steering"
  ],
  "start_distance_m": 0,
  "end_distance_m": null,
  "resolution_m": 2
}
```

Return aligned telemetry for both laps.

Also calculate when possible:

- speed delta
- estimated cumulative time delta
- brake-point differences
- throttle pickup differences

Prefer elapsed-time differences at shared distance crossings when recorded timestamps support them. Otherwise reconstruct elapsed time by integrating distance over speed, with explicit handling of stopped samples, reversals and gaps.
Document the methodology.
Do not pretend it is an exact official timing delta if it is reconstructed.

## Phase 4 — Progressive querying

Design all MCP descriptions so an LLM naturally follows this workflow:

```text
list_sessions
      ↓
get_session_info
      ↓
list_laps
      ↓
get_lap_summary
      ↓
compare_laps at low resolution
      ↓
identify interesting area
      ↓
compare_corner / compare_braking_zones
      ↓
get_telemetry at high resolution
```

The corner/braking comparison branch activates only after Phases 12/13 pass. For the current core, identify a bounded section using coarse elapsed-delta changes and control-point differences, then query that same section on both laps. See [the progressive workflow](docs/progressive-querying.md).

The model should not normally request full-resolution data for an entire lap.
Tool descriptions should explicitly encourage progressive investigation.

## Phase 5 — Safety and query limits

The MCP must be strictly read-only.
DuckDB connections:

```python
duckdb.connect(path, read_only=True)
```

Do NOT expose arbitrary SQL as a normal MCP tool.
Internally parameterise queries.

Enforce configurable limits such as:

```python
MAX_CHANNELS = 20
MAX_LAPS_PER_REQUEST = 10
MAX_OUTPUT_SAMPLES = 5000
MAX_DISTANCE_RANGE_HIGH_RES_M = 2000
DEFAULT_RESOLUTION_M = 2.0
MIN_RESOLUTION_M = 0.1
```

If a query would exceed limits, return a structured error suggesting:

- smaller distance range
- lower channel count
- lower resolution
- querying one corner at a time

Never silently truncate telemetry unless the response clearly reports that truncation occurred.

## Phase 6 — Efficient data representation

Optimise MCP output for LLM consumption.

Prefer:

```json
{
  "distance_m": [100, 101, 102],
  "speed_kph": [210, 207, 202],
  "brake": [0, 0.2, 0.7]
}
```

instead of:

```text
[
  {
    "distance_m": 100,
    "speed_kph": 210,
    "brake": 0
  },
  ...
]
```

For summaries, return compact scalar metrics.

Round floating-point values sensibly:

- distance: ~0.1 m
- speed: ~0.1 km/h
- controls: 3 decimal places
- time: milliseconds where useful

Do not destroy precision internally.

## Phase 7 — Caching

Telemetry alignment and derived metrics can be expensive.

Implement in-process caching for:

- schema inspection
- channel mapping
- lap boundaries
- distance-aligned laps
- braking-zone detection
- corner detection

Cache keys should include:

- session
- lap
- requested channels
- resolution
- relevant analysis settings

Invalidate cache when the telemetry file's modification timestamp changes.
Do not modify the DuckDB.

## Phase 8 — Testing

Create tests for:

### Schema detection

- alternate channel names
- missing optional channels
- unknown columns

### Lap detection

- normal laps
- incomplete first lap
- incomplete final lap
- lap number reset

### Alignment

- different channel sample rates
- missing samples
- interpolation
- discrete channels

### Braking zones

- proper brake event
- light brake tap
- overlapping events
- truncated events at lap boundaries

### Query protection

- too many channels
- too fine resolution
- giant distance range
- path traversal, absolute paths outside the root, and junction/symlink escapes
- locked files, unsupported schemas, new recordings, and cache invalidation
- response-size limits and explicit truncation/pagination
- read-only behavior and unchanged original database files

### Comparison

Use synthetic telemetry so calculations can be checked exactly.
Tests should not require Le Mans Ultimate to be installed. Run focused tests for every change, with tests for corrected defects and new behavior. At each milestone run the complete applicable suite and an MCP client integration test (initialize, tools/list and tools/call), including Streamable HTTP. Test launcher startup, occupied-port handling, failed readiness and process cleanup. Add an optional read-only smoke test against real LMU telemetry; keep private databases out of fixtures and Git. Record commands, outcomes and any untested external dependencies.

## Phase 9 — CLI

Provide commands such as:

```bash
lmu-mcp inspect "session.duckdb"
```

```bash
lmu-mcp serve
```

The command uses the fixed telemetry directory automatically. Resolve inspect/diagnose session filenames relative to that directory; reject paths outside it.

Provide both MCP stdio and Streamable HTTP in Milestone 1, sharing the same analysis layer. Streamable HTTP is required for the requested ChatGPT/ngrok workflow; it is not deferred.

Bind HTTP to `127.0.0.1:18765`. This port passed a local bind test during inspection, but no port is permanently guaranteed free: recheck at every startup and fail clearly if occupied. Do not kill another listener or silently select a different port.

Provide `startLeMansMCP.ps1` in this directory and a copyable PowerShell profile function named `startLeMansMCP`. Leave profile installation to the user. The command must:

1. Validate the fixed telemetry directory, dependencies, ngrok availability and the fixed port.
2. Start the server, verify readiness, then start ngrok for that port.
3. Print the full HTTPS MCP URL suitable for ChatGPT, including its private random path.
4. Detect startup failures and unexpected child-process exits.
5. Stop only processes it started on failure or Ctrl+C; run background helpers with hidden windows.

Keep the random path stable in ignored local configuration so restarting does not unnecessarily change the MCP path. Treat it as a bearer secret for this personal project: anyone with the full URL can access the exposed telemetry. Avoid logging it in access logs; display it only for user setup. Support rotation, keep secrets out of Git and document this personal-use access model. Retain MCP Host/Origin validation and configure ngrok host forwarding appropriately. Do not claim a remote test passed unless a real remote connection was exercised.

## Phase 10 — Diagnostics

Add:

```bash
lmu-mcp diagnose session.duckdb
```

It should report:

```text
Database readable: yes
Tables discovered: 4
Lap channel: found
Lap distance: found
Speed: found
Brake: found
Throttle: found
Steering: found
Gear: found
ABS: found
TC: found
```

```text
Detected laps: 23
Usable laps: 21
Maximum sample frequency: 100 Hz
```

Also warn about important missing channels.

## Phase 11 — Documentation

README should explain:

- installation
- the fixed LMU telemetry location and missing-directory troubleshooting
- starting MCP
- adding it to an MCP client
- tool descriptions
- example coaching workflow
- query limits
- security/read-only behaviour
- troubleshooting
- Windows launcher/profile installation and ngrok configuration
- ChatGPT connection using the printed HTTPS MCP URL
- random-path privacy limits, rotation, and keeping credentials out of Git
- recorded-session availability, timing uncertainty, missing validity and comparison limitations

Include example questions:
Find my fastest three valid laps, or benchmark candidates if official validity is unavailable.

Compare my fastest lap with my second-fastest lap and tell me where the major differences occur.

Analyse braking consistency across my five fastest laps.

Look closely at the braking zone between 5200 m and 5450 m.

Compare my brake release and throttle pickup through corner 7.

## Phase 12 — Braking analysis

Implement:

### `get_braking_zones`

Input:

```json
{
  "session_id": "...",
  "lap": 12
}
```

Detect braking events based on configurable brake thresholds.
For each event return:

```json
{
  "zone": 4,
  "start_distance_m": 5231,
  "end_distance_m": 5382,
  "initial_speed_kph": 281,
  "minimum_speed_kph": 112,
  "peak_brake": 0.98,
  "duration_s": 2.41,
  "distance_m": 151,
  "abs_active_time_s": 0.15
}
```

Thresholds must be configurable.
Avoid treating tiny brake taps as full braking zones.

### `compare_braking_zones`

Inputs:

```json
{
  "session_id": "...",
  "lap_a": 7,
  "lap_b": 11
}
```

Match braking zones approximately by track position.

Return differences in:

- braking start
- braking distance
- initial speed
- minimum speed
- peak brake
- brake release
- throttle pickup
- ABS usage

This will be one of the primary coaching tools.

## Phase 13 — Corner analysis

Implement a basic automatic corner detector using:

- lateral acceleration
- steering
- speed profile
- optionally yaw rate

Do not over-engineer track-map reconstruction initially.
Expose:

### `get_corners`

Return approximately:

```json
{
  "corner_id": 8,
  "start_distance_m": 8212,
  "apex_distance_m": 8274,
  "end_distance_m": 8371,
  "entry_speed_kph": 188,
  "minimum_speed_kph": 126,
  "exit_speed_kph": 171
}
```

Allow the algorithm to be refined later.
Also allow manually defined track corner ranges through optional configuration files.
Manual definitions should override automatic detection.
Example:

```text
tracks/
    le_mans.json
    spa.json
```

### `compare_corner`

Inputs:

```json
{
  "session_id": "...",
  "corner_id": 8,
  "laps": [7, 11]
}
```

Return:

- brake point
- turn-in position
- apex/min-speed position
- minimum speed
- throttle pickup position
- full-throttle position
- entry speed
- exit speed
- approximate time through the section
- ABS/TC intervention
- steering metrics

## Important implementation principle

Separate these layers:

```text
MCP interface
     ↓
Telemetry analysis API
     ↓
Schema abstraction
     ↓
DuckDB repository
```

The core telemetry-analysis functions must be callable directly from Python without MCP.
For example:

```python
telemetry.compare_laps(...)
```

should work independently of:

```python
@mcp.tool()
def compare_laps(...):
    ...
```

This will make the project testable and allow building other interfaces later.

## First implementation milestone

Do NOT try to implement everything at once.

Start with a working vertical slice containing:

- session discovery
- DuckDB schema inspection
- automatic channel mapping
- list_sessions
- get_session_info
- list_laps
- get_lap_summary
- get_telemetry
- compare_laps
- tests
- CLI
- README
- diagnostics
- Streamable HTTP on port 18765
- Windows launcher and ngrok integration

After all Milestone 1 gates (Phases 1-11) pass, proceed in order to:

- braking zones
- corner detection
- advanced coaching metrics

Before coding schema-specific logic, inspect the actual supplied LMU DuckDB database and show me:

- discovered tables
- important columns
- inferred channel mapping
- proposed adaptations

Then implement against what is actually present rather than guessing LMU's schema.

## Acceptance criteria for milestone 1

I should be able to run:

```bash
lmu-mcp serve
```

Then an MCP client should be able to:

```text
list_sessions()
list_laps(session)
compare_laps(session_id=session, laps=[lap_a, lap_b])
get_telemetry(session, lap, 3000m → 3500m)
```

without loading an entire race session into the model context.
A typical query covering a corner should return a few hundred to a few thousand values, not hundreds of thousands.
All DuckDB access must remain read-only. The Windows `startLeMansMCP` command must start the server and ngrok, print a usable HTTPS MCP URL and clean up owned processes on exit. Report local protocol verification separately from actual ngrok/ChatGPT verification.
Start by creating the project scaffold and implementing Milestone 1.
