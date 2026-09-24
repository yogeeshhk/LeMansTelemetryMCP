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

Scope is sourced general track coaching followed, when requested, by personal analysis of recorded telemetry, not a live shared-memory plugin. Preserve original DuckDB files. Do not expose arbitrary SQL, database writes, arbitrary filesystem reads or a frontend. Provide fuel/tyre statistics and compact coaching context through the summary/channel tools where supported; avoid duplicating tools merely to give them coaching-oriented names.

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
| 4: track-aware personal coaching | 14-19, sequentially | Sourced guides for La Sarthe, Spa and Monza (Monza explicitly approximate), tested likely-excursion patterns and evidence-based setup experiments, bounded MCP protocol coverage and read-only real-file checks. |

Do not start the next milestone until the current exit gate passes. Do not silently omit a phase, replace its requirements with placeholders, or call a partially tested milestone complete. If external access blocks a check, record the blocker and keep that gate open. Only tested, committed implementation counts toward phase completion.

For each small implementation step: make the change, run relevant tests/checks, update this plan's progress log with evidence, and create a focused Git commit before starting the next step. Run the complete applicable test suite at milestone boundaries. Documentation-only steps require document/link/consistency checks rather than unrelated application tests.

### Progress log

- Phase 16, step 1 complete: extended version-1 packs with optional bounded coaching notes (evidence, applicability and source references), exposed them through the unchanged guide input contract, and clarified general-guide use in the tool description. This small content extension is needed now for the Phase 16 coaching standard; the La Sarthe/server-wide workflow audit remains Phase 19. Synthetic focused suite: `python -m pytest tests/test_phase16_coaching.py tests/test_phase14_guide.py tests/test_phase14_packs.py tests/test_phase15_pack.py -q` using the project virtual environment: 14 passed, 1 Windows symlink-privilege skip. Checked note bounds, unknown evidence/sources, compatibility, pagination and no lap/path dependency; Markdown fences/local links and `git diff --check` passed. Initial system-Python inspection lacked the package; subsequent inspection used `.venv`. Reviewed five distance-valid Spa laps read-only with unchanged hash/size/mtime/WAL state; original GPS values cannot be treated as Earth coordinates. Spa pack, split/merged association coverage and final protocol/smoke checks remain.

- General track-guide planning update complete: recorded the user's Qatar guide as a style/depth reference and added the general-guide-first content, evidence, query-routing and acceptance contract. Assigned remaining pack coverage to Phases 16/17 and the La Sarthe/workflow audit to Phase 19 without changing phase order or prior completion history. Documentation checks passed for 19 sequential phase headings, balanced fences, seven link targets (local existence and external URL syntax), unchanged milestone table and command/code blocks, and workflow/acceptance consistency; `git diff --check` passed. The example page was read through web search in the preceding discussion after direct access returned HTTP 429; external links were not freshly fetched for this prose edit. No application tests were run or new coaching behavior declared implemented. Public ngrok/actual ChatGPT checks remain open.

- Phase 15, step 3 and phase acceptance complete: full `python -m pytest -q` passed 130 tests with 3 expected skips. Wheel/sdist build passed and both archives contain the La Sarthe JSON pack. A separate read-only smoke on the supplied recording returned the 15-feature sourced guide, four uniquely named/calibrated corners on each of laps 1 and 2, and 9/10 unnamed detections. `compare_corner` matched Tertre Rouge across those benchmark laps by measured start distance and retained its normal metric-delta contract. The original DuckDB SHA-256, size and modification time were unchanged. Phase 15 accepted; Phase 16 Spa is next. The previously skipped public ngrok/actual ChatGPT integration gate remains open.

- Phase 15, step 2 complete: added regression tests that reject a shifted Indianapolis boundary or missing feature, and verify that an ACO source-date revision updates both `get_track_guide` and cached `get_corners` provenance without changing measured speed. A local HTTP MCP client queried the actual packaged La Sarthe guide from synthetic exact-layout metadata, checked pagination/source/absence of driver values and received a missing-session tool error. Updated README/core/testing docs for the active pack. Focused `python -m pytest tests/test_phase15_pack.py tests/test_phase3_mcp.py -q`: 13 passed; seven Markdown files passed fence/local-link checks and `git diff --check` passed. Final full suite, packaging and read-only supplied-recording smoke remain.

- Phase 15, step 1 complete: added an exact-layout La Sarthe pack with 15 ordered source-backed features from the ACO 2026 turn-by-turn guide, ACO 2021 venue map and ACO 2025 regulation map. Three complete distance-valid laps in the supplied recording yielded four stable, unique single-corner associations (Tertre Rouge, Mulsanne Corner, Indianapolis, Arnage) on every reviewed lap; 9, 10 and 12 other detected ranges remained unnamed. Multi-turn chicanes/curves remain guide complexes; broad straights are approximate, and unsupported individual boundaries are unmatched. The pack guide records source date, edition/naming caveats, telemetry calibration method and uncertainty without private lap/GPS/driver data. Focused `python -m pytest tests/test_phase15_pack.py tests/test_phase14_packs.py -q`: 6 passed, 1 Windows symlink-privilege skip; guide links/fences and `git diff --check` passed. Synthetic shifted-boundary/source-revision protocol tests and final read-only/full-suite checks remain.

- Phase 14, step 4 and phase acceptance complete: the complete `python -m pytest -q` suite passed 124 tests with 3 expected skips (two opt-in real-file tests and unavailable Windows file-symlink privilege). Synthetic pack loading, exact/unknown layout, malformed/duplicate/escaped packs, pagination, edit invalidation, manual priority, ambiguous associations and sourced names were covered, including actual stdio/HTTP MCP success and invalid-input calls. `python -m build --wheel --sdist --outdir .\build\phase14` passed; both archives contain `track_knowledge.py`, `calibration.py`, the new MCP tool and the pack guide. A separate read-only supplied-recording smoke returned `no_pack` and left SHA-256, size and mtime unchanged. The pack-authoring/calibration docs and local links/fences passed validation. No real named pack is included in Phase 14; Phase 15 will calibrate La Sarthe. The previously skipped public ngrok/actual ChatGPT integration gate remains open.

- Phase 14, step 3 complete: registered read-only `get_track_guide` with exact-layout paged features, `no_pack`, source/uncertainty/status and bounded typed inputs. Unique sourced corner matches enrich automatic `get_corners` and `compare_corner` results without changing measured metrics; exact manual overrides retain priority. Pack contents enter the corner cache key, so edits invalidate derived names. Server guidance and user docs now distinguish measured ranges from sourced names. Synthetic guide/manual/edit-invalidation tests and actual stdio/HTTP MCP clients, including a sourced synthetic HTTP call and invalid input: `python -m pytest tests/test_phase14_guide.py tests/test_phase3_mcp.py -q`: 11 passed. Seven Markdown files had balanced fences and valid local links; `git diff --check` passed. Final Phase 14 full-suite, packaging and read-only supplied-recording checks remain.

- Phase 14, step 2 complete: added direct-Python and local CLI `calibration-report` that inspects at most five complete laps, prioritizes benchmark candidates, reports automatic turn ranges, optional rounded GPS apex evidence, unique candidate pack associations and explicit unsupported-path codes. Incomplete intervals are skipped with a count; no driver/setup values are emitted and the command does not write artifacts or original files. Focused calibration/pack tests: `python -m pytest tests/test_phase14_calibration.py tests/test_phase14_packs.py -q`: 7 passed, 1 skipped for unavailable Windows file-symlink privilege. A separate read-only supplied-recording smoke inspected two laps and 27 detected ranges with unchanged SHA-256, size and mtime. Pack guide now documents the command. MCP guide/enrichment and final Phase 14 checks remain.

- Phase 14, step 1 complete: added an offline versioned track-knowledge loader under `tracks/knowledge`, separate from user manual-corner overrides, with exact track/layout matching, source provenance, feature order/status/range checks, corner nonoverlap, 32-file/64-KiB bounds and path confinement. Added pack-authoring guide and package-data inclusion; no real named pack was activated. Synthetic loader plus legacy manual tests: `python -m pytest tests/test_phase14_packs.py tests/test_phase13_manual.py -q`: 7 passed, 1 skipped (file symlink privilege unavailable). Wheel/sdist build passed and included loader/guide. Calibration report, public tool, corner enrichment and milestone verification remain Phase 14 work.

- Milestone 4 planning step complete: added sequential Phases 14-19 for sourced track knowledge, calibrated La Sarthe/Spa packs, an explicitly approximate Monza pack, likely excursion hotspots, and car-applicable setup experiments with bounded recent/general history. Documented exact recorded layout names, source/provenance and confidence rules, MCP tool contracts, phase exit checks and post-milestone layout expansion. Preserved completed Milestones 1-3 and the open public ngrok/ChatGPT gate. Documentation-only checks: 19 consecutive phase headings, balanced Markdown fences, milestone/table/tool/command consistency and six local/external links validated; the five external source pages opened successfully; `git diff --check` passed. Application tests were not rerun because this step changes only the plan.

- Phase 13 and Milestone 3 feature acceptance complete: final post-fix `python -m pytest -q` passed 112 tests with 2 expected skips (Windows file-symlink privilege and opt-in real smoke). A separate read-only supplied-recording check successfully compared a matched corner on two benchmark candidates; automatic discovery returned 13 and 14 ranges, and the original SHA-256, size and modification time stayed unchanged. Local stdio and HTTP MCP protocol, package contents and Markdown checks are recorded in step 4. No public ngrok tunnel or actual ChatGPT coaching session was run because the user chose to skip the live test; the Milestone 1 remote integration gate remains open.

- Phase 13, step 4 complete: registered read-only `get_corners` and `compare_corner` with bounded typed inputs and coaching guidance, updated the eleven-tool README, numerical method and progressive workflow. Actual stdio and local HTTP MCP clients initialized, discovered and successfully called all eleven tools, including corner success and unknown-corner error. A read-only supplied-recording smoke found a small negative lap-distance start on one candidate lap; automatic scanning now clips its requested grid to 0 m while retaining the original path, with a synthetic regression. Focused `python -m pytest tests/test_phase13_service.py tests/test_phase3_mcp.py -q`: 10 passed. Markdown links/fences/tool references and wheel/sdist Phase 13 contents passed. A real-file recheck detected 13 and 14 corner ranges on two candidates, with 11 reference starts within the 100 m matching window; one queried unmatched corner was reported explicitly. Original source hash/size/mtime remained unchanged in the read-only smoke. Final full-suite rerun after the negative-start fix remains the Phase 13 exit check; public ngrok and actual ChatGPT validation remain open by prior user choice.

- Phase 13, step 3 complete: added direct-Python `get_corners` and `compare_corner` over the validated distance path. Manual exact track/layout definitions override automatic detection; automatic corners use verified `%` steering, `G` lateral acceleration and km/h speed. Per-corner results include entry/minimum/exit speed, minimum-speed/apex position, brake/turn-in/throttle positions, approximate section time, optional ABS/TC active and coverage time, steering metrics and quality flags. Comparison accepts 2-5 distinct benchmark candidates, matches manual IDs exactly or automatic starts within 100 m, and suppresses deltas with quality flags. Two-metre metric sampling means the reported minimum need not equal a native sample minimum. Synthetic service tests for known metrics/comparison, manual override and edit invalidation, outside coverage and request errors: `python -m pytest tests/test_phase13_service.py -q`: 3 passed. MCP registration and milestone checks remain.

- Phase 13, step 2 complete: added optional exact-match track/layout JSON corner definitions under `src/lmu_mcp/tracks/`, with fixed-directory path confinement, 32-file/64-KiB bounds, nonoverlapping <=2000 m ranges, unique IDs and optional names/apex positions. Matching manual ranges will override automatic detection; no real track definition or corner name is invented. The editable-install directory contains a schema guide and package data includes it. Synthetic exact-match, invalid range/apex/ID, duplicate/invalid JSON and size/count checks plus detector tests: 8 passed. Wheel and sdist builds contain the loader and guide. Service integration and MCP tools remain Phase 13 work.

- Phase 13, step 1 complete at the user's request for the next phase while public remote validation remains open: added a pure automatic corner-range detector using verified steering percent, lateral acceleration in G and speed profile on increasing distance samples. It requires sustained steering/lateral load, joins only short fully observed holes, ignores tiny spikes, keeps missing-data gaps separate, and returns unnamed ranges with approximate minimum-speed apexes. Synthetic known-turn, spike, gap and invalid-input tests: `python -m pytest tests/test_phase13_detector.py -q`: 4 passed. Manual definitions, per-corner metrics, comparison, MCP tools and documentation remain Phase 13 work.

- Phase 12 implementation complete, step 3: registered read-only `get_braking_zones` and `compare_braking_zones` with typed bounded thresholds and tool guidance; updated the nine-tool README, core methodology, progressive workflow and testing docs. Actual stdio and HTTP MCP clients initialized, discovered all nine tools and called both new tools; the HTTP regression checked a known matched zone and invalid-threshold error. Added service edge tests for missing speed coverage and partial onset exclusion. Focused affected suite: 17 passed; final full `python -m pytest -q`: 100 passed, 2 skipped (Windows file-symlink creation unavailable and opt-in real smoke skipped by default). A separate read-only supplied-recording smoke query detected and compared zones on benchmark candidates, matched 14 zones, and left original SHA-256, size and mtime unchanged. Wheel and source-distribution builds include both braking modules; documentation links/fences/tool names/thresholds/units and Git diff check passed. Default detection uses 10% onset, 5% release, 0.3 s minimum duration, 20% peak and 5 km/h speed drop; ordered matching defaults to 100 m. Producer percent is returned as `peak_brake_pct` rather than the plan example's unit-ambiguous `peak_brake` fraction. Phase 12 feature acceptance is met. The user previously chose to skip public ngrok/ChatGPT tests, so Milestone 1 external validation remains open and no public integration result is claimed.

- Phase 12, step 2 complete: connected braking analysis to the validated read-only session, clock and monotonic distance path. Direct Python methods `get_braking_zones` and `compare_braking_zones` report speed, braking distance, peak percent brake, optional ABS active time, bounded throttle pickup, quality flags, unmatched zones and A-minus-B metric differences. Comparisons require benchmark candidates and pair only fully observed zones; analysis settings are validated before database access and included in revision-aware cache keys. Synthetic 10 Hz/5 Hz recording checks known zone distances, speed/ABS/pickup and comparison deltas, threshold filtering, missing ABS as null, invalid settings and source-change invalidation. Focused `python -m pytest tests/test_phase12_service.py tests/test_phase12_braking_core.py -q`: 9 passed. MCP registration, protocol tests, real-file smoke and documentation remain Phase 12 work.

- Phase 12, step 1 complete at the user's explicit request for the next phase while Milestone 1 public validation remains open: added a transport-independent hysteresis brake-interval detector with bounded configurable thresholds, percent-unit range checks, gap/missing-sample splitting and tap filtering, plus ordered one-to-one track-position matching. The initial synthetic run exposed an incorrect test expectation for a post-gap event; corrected the expectation to assert three separate events. Final `python -m pytest tests/test_phase12_braking_core.py -q`: 4 passed. Service enrichment, public tools, integration tests and documentation remain Phase 12 work; no remote endpoint was exercised.

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

For personal lap analysis, design all MCP descriptions so an LLM naturally follows this workflow. General track-guide requests first follow the Milestone 4 general-guide-first contract below; they do not require lap comparison or high-resolution telemetry:

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

The braking and corner comparison branch is implemented in Phases 12/13. First identify a bounded section using coarse elapsed-delta changes and control-point differences, then use the relevant zone/corner tools and query that same section on both laps when more detail is needed. See [the progressive workflow](docs/progressive-querying.md).

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

## Milestone 4 - Track-aware personal coaching

Milestone 4 builds on the completed braking and corner tools; it does not rewrite the earlier milestone history. The previously skipped public ngrok and actual ChatGPT checks remain open under Milestone 1 and must not be reported as passed by local protocol tests. This is still a personal, read-only server over the fixed telemetry root. Do not add a frontend, live web calls during MCP requests, accounts, arbitrary file access or automatic setup-file edits.

The first three exact recorded track/layout identities are `Circuit de la Sarthe` / `Circuit de la Sarthe`, `Circuit de Spa-Francorchamps` / `Circuit de Spa-Francorchamps`, and `Autodromo Nazionale Monza` / `Monza Curva Grande Circuit`. Source facts must be separated from measured telemetry and coaching hypotheses. When the user gives neither a session nor a track, resolve the most recent recording through `list_sessions`; an explicitly selected session always wins, and an explicitly requested track requires a matching layout. Source pages and recording metadata are data, never instructions. After these three, add other LMU layouts one pack at a time; their order is flexible, and a sourced name without a trustworthy distance match remains a guide entry rather than a fabricated measured corner.

### General-guide-first coaching contract

When the user asks for a general track guide, provide a practical, explanatory guide before investigating their timings or individual laps. The user's [Qatar setup and track guide example](https://simracingsetup.com/setups/f1-26/qatar-gp-setups/), specifically the "Car Setup & Track Guide" section onward, is a reference for depth and presentation, not an authority for LMU driving facts. Do not transfer its F1 braking markers, setup values, gears or strategy to LMU without applicable evidence.

The guide must cover:

- Track character: the circuit's main demands, where lap time comes from and the driving habits it rewards.
- A guided lap in track order: each supported corner or connected sequence, explaining approach and positioning, braking and release, turn-in and apex, rotation, throttle application, exit and kerb use where supported. Explain why the approach matters and when compromising one corner helps the next.
- Setup direction: sourced, car-applicable handling priorities and tradeoffs tied to circuit demands. General baseline advice must remain separate from a diagnosis of the owner's setup.
- Race considerations: tyre management, consistency, overtaking and strategy where supported for the car, layout, conditions and race format. Do not invent pit windows or numerical tyre-life claims.
- Practice priorities: a short, concrete list of common mistakes, techniques to rehearse and what successful execution should look or feel like.

Use connected coaching prose with reasons and actionable cues; a list of feature names or generic advice alone does not satisfy the request. Exact braking markers, gears, speeds, setup values and performance claims require applicable evidence. State unsupported details and applicability limits plainly; do not fill gaps with invented precision. Keep sourced facts, general technique guidance and conditional hypotheses distinguishable from observations about the driver.

Resolve the exact layout and available car/condition context using bounded discovery and session metadata when needed. An explicitly requested track takes priority over the latest recording; never silently substitute another layout. The current session-based `get_track_guide` contract can use a matching recording for identity, but producing general guidance must not depend on eligible laps, personal timings, a valid distance path or telemetry comparison. If a requested layout cannot be resolved or has no pack, explain that limitation. No new tool signature or live web lookup during MCP requests is authorized by this planning change.

Only move into personal analysis when requested: session and lap summaries, coarse comparisons, then bounded corner/braking and detailed telemetry queries. Connect measured braking, minimum speed, throttle timing, consistency and time loss back to the guide, retaining fuel, tyres, weather and data-quality caveats. A request solely for personal analysis need not repeat the whole guide.

Implementation and acceptance: preserve Phases 14-19 in order and their recorded completion history. Apply this content standard to remaining packs in Phases 16/17; in Phase 19, audit and extend the earlier La Sarthe pack, bounded guide content/schema as needed, server instructions and progressive-workflow documentation. This new requirement remains pending until that work passes review. Verify a full guide with no personal lap metrics, a guide with unusable lap-distance data, explicit-track precedence, missing-pack handling, unsupported car-specific details and a subsequent personal-analysis request. Test changed structured content, bounds and protocol behavior with synthetic data and actual local MCP clients; separately review representative coaching responses for coverage, explanations and evidence separation. Local checks do not establish actual ChatGPT behavior; retain its separate external gate.

### Shared contracts and review rules

- Keep a bounded, versioned, package-local track-knowledge format separate from the existing user-editable manual corner override. Match exact `TrackName` and `TrackLayout` only. A user manual definition keeps its existing priority; a curated pack can enrich a measured automatic corner only when the association is unique. An approximate pack must never silently replace a validated distance path or turn an unsupported lap into an eligible benchmark.
- Each feature has a stable local ID, name, kind (`corner`, `complex`, `straight`, `sector` or `landmark`), order, source references and one of `calibrated`, `approximate` or `unmatched`. Add metre ranges and uncertainty only when supported. Return source title, URL and retrieval date with each externally sourced claim; keep a short explanation of how its distance was assigned. No copied articles or unbounded web content is packaged.
- The implementer reviews official circuit/game sources and a local calibration report before activating a pack. Cross-check feature order against the source map and at least two usable laps when available; use GPS and steering/lateral/speed traces as evidence without treating a map image as exact LMU lap distance. Leave uncertain associations unnamed. Document any intentional limitation in the pack and plan progress log.
- A coaching result must distinguish recorded observations, derived estimates, sourced track/setup facts and testable hypotheses. Preserve units, lap eligibility, setup availability, weather/fuel/tyre context, gaps and coverage. A single slow corner or one likely excursion does not prove understeer, oversteer or a setup defect.
- New MCP tools retain the current read-only annotations, typed bounded inputs, compact JSON, safe errors, fixed-root confinement and worker execution. Internal analyses remain callable directly from Python. Include pack content and analysis settings in bounded cache keys so edits invalidate results. Never include private telemetry or setup values in committed fixtures or source packs.

## Phase 14 - Track-knowledge foundation

1. Add the versioned pack loader and validator under the existing package tracks area. Validate exact metadata identity, unique feature IDs, ordered corner ranges without corner-to-corner overlap, allowed kinds/status, source URLs and bounded file count/size. Straights, sectors and landmarks may overlap corner ranges when the source defines them that way. Reject duplicate matching packs, path escapes and invalid UTF-8/JSON. Preserve legacy manual-corner behavior and its precedence. No network request occurs while serving MCP.
2. Add a local, read-only calibration report command or internal script that lists eligible laps, detected turn ranges, GPS/turn evidence, candidate feature associations and unsupported gaps without publishing private driver data. It may write review artifacts only to an ignored local directory; no original DuckDB/WAL write or path repair is allowed.
3. Add `get_track_guide(session_id, offset=0, limit=50)`: return the exact layout, pack status, paged ordered features, units, source provenance, uncertainty and `next_offset`. Unknown layouts return an explicit `no_pack` status. Enrich `get_corners` and `compare_corner` with a unique supported feature association and provenance; never overwrite measured speed/time/quality metrics. Update server instructions to request the guide only when named track context helps answer the question.
4. Test exact-match/unknown-layout, duplicate/invalid/escaped packs, pagination and response limits, edit invalidation, legacy manual priority, ambiguous associations, stdio/HTTP MCP success and errors. Validate wheel/sdist contents and document the pack-authoring/calibration process. Exit when a synthetic pack can be reviewed and queried end-to-end without changing original telemetry.

## Phase 15 - La Sarthe calibrated pack

Use the [ACO Le Mans venue map](https://assets.lemans.org/explorer/pdf/courses/2021/24-heures-du-mans/presse/dossier-de-presse-24-heures-du-mans-2021-GB.pdf) and any newer primary source whose layout matches the recording. Record source date and layout caveats. Build the full-lap sequence of supported named corners, complexes, straights and major landmarks; do not invent a name for every automatically detected turn. Calibrate candidate distance ranges against at least two distance-valid La Sarthe laps using the Phase 14 report, then audit ordering, unique associations and uncertainty. Add corner-character notes only when sourced. General driving guidance follows the general-guide-first contract; claims about the owner's driving still require measured lap evidence.

Exit when `get_track_guide` returns the sourced pack, named associations in `get_corners` are unique and carry calibration status, unmatched detections remain unnamed, and `compare_corner` retains its current measured differences. Synthetic shifted-boundary, missing-feature and source-revision tests plus a read-only supplied-recording smoke must pass; record source-file hash/size/mtime unchanged.

## Phase 16 - Spa calibrated pack

Use the [Spa-Francorchamps circuit operator map](https://www.spa-francorchamps.be/assets/e70cff50-ae5d-4aaa-896b-54c8a953a357/all-plan-acces.pdf) and matching official layout material. Repeat the source/order/distance review on at least two distance-valid Spa laps. Treat named sequences such as Eau Rouge/Raidillon and multi-turn complexes as source-defined features; do not force one feature per automatic range. Test exact `Circuit de Spa-Francorchamps` layout matching, multi-turn/merged detections, weather or gap limitations, and the same guide/corner/provenance behavior as Phase 15. Exit after full local protocol and read-only Spa smoke checks with unchanged original files.

## Phase 17 - Monza approximate pack

Use the [Monza circuit operator description and map](https://www.monzanet.it/en/circuit/) for named order and track character. Publish an explicitly `approximate` guide for the exact `Monza Curva Grande Circuit` layout, with bounded estimated distance ranges and visible uncertainty. The currently available Monza intervals fail the validated lap-distance path because of distance reversals: `get_track_guide` must still work, while `get_corners`/comparison must keep their actionable `distance_reversal` error. Do not repair or sort the source path. When a future usable lap exists, associate a name only to a uniquely matched detected range and retain the approximate flag until calibrated. Test this current-file limitation, unknown variants, approximate-label propagation and later calibration replacement. Exit when the guide is useful without claiming current Monza corner metrics were verified.

## Phase 18 - Likely excursion patterns

Inspect the meaning, sign, sampling and units of `Path Lateral`, `Track Edge`, `SurfaceTypes` and GPS against source documentation and recorded traces before defining an excursion predicate. Use sustained observations with validated distance/time coverage; split at missing samples, clock gaps and lap resets. Treat surface-type codes as unknown until verified. If the signals cannot support a specific event, return `unsupported` or an unconfirmed path deviation, not an official track-limit violation.

Add `get_excursion_hotspots(session_id, scope='recent', offset=0, limit=50)`. `recent` uses the selected recording; `general` scans at most five recent recordings of the same exact layout and car and at most 30 complete distance-valid laps. Include complete flagged laps for excursion counting, but never treat them as clean pace benchmarks. Return bounded event counts, distinct affected laps/sessions, distance ranges, associated named feature when supported, coverage, confidence and explicit truncation. Tests must cover repeated events, short noise, opposite edge signs, missing/ambiguous signals, gaps, partial laps, mixed cars/layouts and cost bounds. Exit after synthetic and read-only real-file validation, with uncertainty documented.

## Phase 19 - Corner history and setup experiments

Parse the recorded `CarSetup` JSON through a fixed allowlist of known adjustable keys. Validate `available`, raw value and declared range, preserve producer labels, and omit unsupported settings without guessing click direction or wheel/component order. Keep private setup values out of source packs, tests, logs and Git. Use car-applicable primary sources such as the [LMU setup guide](https://lemansultimate.com/lmp3-quick-setup-guide/) and [LMU traction-control guide](https://guide.lemansultimate.com/hc/en-gb/articles/13182869047311-How-do-I-configure-my-traction-control-in-Le-Mans-Ultimate); do not generalize a car-specific rule to other cars.

Add `get_corner_history(session_id, corner_id, scope='recent')`. In `recent`, analyze the selected recording. In `general`, use the same bounded exact-layout/car session search as Phase 18: select up to three fastest benchmark-candidate laps and up to three slowest complete distance-valid laps by supported recorded timing, disclosing timing source, quality flags, selection and sample count. If timing is unsupported, return no pace ranking rather than sorting by guessed times. Return repeated entry/mid/exit evidence, likely-excursion overlap, condition differences, relevant current setup context and at most three ranked one-setting experiments. Each experiment states a conditional symptom, proposed direction only when verified, expected tradeoff, source and a next-run measurement; numerical changes require verified car-specific setting semantics. If evidence is weak, return observations and a driving test or a request for driver feedback instead of a setup claim. Do not write game setup files.

Exit after synthetic good/bad-history, setup-availability, wrong-car source, missing wheel mapping, mixed conditions, unsupported signal and no-advice cases; actual stdio/HTTP client tests must cover both new coaching tools and errors. Run the full suite, build/package checks and read-only real-file smoke, then update the progressive coaching workflow and pass the general-guide-first content and workflow acceptance checks above. Milestone 4 may be marked complete only with these checks and the three first packs' stated calibration statuses; actual public ngrok and ChatGPT behavior remain a separately reported open check.

### After Milestone 4 - Other LMU layouts

Maintain a sourced checklist of officially available circuit/layout variants and add one exact-match pack per reviewable, tested commit in any order. Prefer calibration where usable telemetry exists; label source-only packs approximate and keep unsupported metric queries unavailable. A newly introduced layout or game update requires a fresh source/identity check rather than reusing a similar layout's ranges. This continuing expansion is not falsely counted as complete when the first three packs pass.

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

Phases 12 and 13 subsequently added braking zones and corner analysis at the user's direction. Their feature gates passed; the Milestone 1 public ngrok/ChatGPT verification remains open. Milestone 4 phases above now define the next track-aware coaching work.

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
