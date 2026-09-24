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

## La Sarthe review (2026-09-25)

`la_sarthe.json` matches only `Circuit de la Sarthe` / `Circuit de la Sarthe`. Its full-lap name sequence follows the [ACO 2026 turn-by-turn guide](https://www.24h-lemans.com/en/news/explore-the-24-hours-of-le-mans-circuit-turn-by-turn-60679). The [ACO 2021 venue map](https://assets.lemans.org/explorer/pdf/courses/2021/24-heures-du-mans/presse/dossier-de-presse-24-heures-du-mans-2021-GB.pdf) shows the older generic ?1st Chicane? label; the 2026 guide calls the first and second Mulsanne chicanes Daytona and Michelin. The [ACO 2025 regulation map](https://assets.lemans.org/explorer/pdf/courses/2025/24-heures-du-mans/regulations/2025-24-hours-of-le-mans-supplementary-regulations.pdf) gives circuit/loop context, including i2, Porsche In/Out and Ford In/Out. These real-circuit sources establish names and order, not exact game telemetry coordinates.

The local read-only calibration report was reviewed on three complete distance-valid laps from the supplied 2026-09-22 recording. It consistently associated four individual corners: Tertre Rouge, Mulsanne Corner, Indianapolis and Arnage. Their pack ranges enclose the detected intervals with explicit uncertainty; all four matched uniquely on each reviewed lap. Dunlop, Daytona, Michelin, Porsche and Ford chicanes/curves remain multi-turn `complex` guide entries, so one detected turn is not silently given the name of the whole sequence. Pit/Mulsanne straights have broad `approximate` ranges. Dunlop Curve, Forest Esses, Karting Esses and Motul Turn stay `unmatched` where this report and source map do not justify an individual measured boundary. A detected range without a unique single-corner match remains unnamed.

The pack stores no driver, setup, lap-time or GPS values. Its metre boundaries are LMU calibration estimates, not surveyed track limits or race-control timing lines. ACO material covers real-world editions from 2021 to 2026; a future game layout revision must be reviewed separately before reusing these distances.

## Optional coaching notes

Version 1 packs may include up to eight top-level `coaching` notes with topic `overview`, `setup`, `race` or `practice`, and up to three notes per feature with topic `driving`. Each note contains printable `text` (1-1000 characters), `applicability` (1-240 characters), `evidence` (`sourced`, `general_technique` or `hypothesis`) and up to five distinct `source_ids`. Sourced notes require at least one valid source. Other notes may cite the map/context behind an inference, but must not present that inference as a source quotation or driver measurement. All notes share the existing 64 KiB file and response-envelope limits.

`get_track_guide` returns top-level coaching on each page and feature coaching with its paged feature. Older packs return an empty top-level coaching list. Distances locate features; they are not recommended braking points. General guidance requires only identity metadata, not eligible laps or reconstructed distance. Personal observations remain in the numerical analysis tools. Exact car settings require applicable evidence; avoid treating historical real-world setup advice as universal current LMU settings.

## Spa review (2026-09-25)

`spa.json` matches only `Circuit de Spa-Francorchamps` / `Circuit de Spa-Francorchamps`. Its 13-feature lap uses the [operator 2026 map](https://www.spa-francorchamps.be/assets/e70cff50-ae5d-4aaa-896b-54c8a953a357/all-plan-acces.pdf), visually reviewed on PDF pages 3 and 4, and the [WEC named-turn map](https://press.fiawec.com/assets/fileuploads/68/12/681245187cd73.pdf). Use the source names Campus, Courbe Paul Frere and Speaker corner; alternative names and game layout variants are not silently substituted. The final Chicane/Bus Stop wording also follows the historical WEC guide cited in the pack.

Five complete distance-valid laps from the latest available Spa practice recording were reviewed with the read-only calibration report. The operator's physical distance markers establish approximate regions; the stored boundaries come from the observed LMU turn intervals and retain uncertainty. The roughly 6980 m recorded coverage is not rescaled to the map's 7004 m. GPS values were in degrees but did not correspond to Spa's Earth location, so no Earth-coordinate calibration was claimed. This sample covered GT3 in recorded Light Clouds; it does not validate wet limits, other cars' optimal lines or braking targets.

La Source, Bruxelles, Speaker corner, Campus and Courbe Paul Frere have calibrated single-corner ranges. Detections sometimes split; a name is attached only when one detected range matches one feature and that feature is not assigned to another detection on the lap. A range overlapping multiple named single corners is also left unnamed. Complexes remain guide context even if the detector produces one merged range. Les Combes, Pouhon, Fagnes and the final chicane have calibrated complex ranges; Eau Rouge/Raidillon and Blanchimont are explicitly approximate because some of the sequence is undetected. Straight boundaries are broad context.

The guide contains general technique notes for every feature, plus overview, setup, race and practice notes. These are conditional teaching cues, not personal findings or optimal-car targets. Source-backed statements carry references; technique and hypothesis labels distinguish interpretation. The historical 2013 WEC setup material supplies context, not current LMU settings. The LMU V1.2 aero-package statement is restricted to Oreca 07 LMP2+ (ELMS Spec), and is not a GT3 recommendation. Current kerb grip, exact brake markers, gears, pressures, wing clicks, pit windows and tyre-life numbers remain unsupported. Pack content is available without lap analysis, including when a path has gaps or reversals; metrics keep their existing errors and flags.
