# Phase 1: schema inspection

Inspection date: 2026-09-23. Scope: the fixed telemetry directory in `plan.md`.

## Discovery and read-only verification

- 59 DuckDB recordings discovered recursively; 57 readable, all with the same table/column/type signature. Two recordings with adjacent WAL files were skipped; no recovery was attempted.
- The supplied race recording contains 104 base tables and no views: 61 sampled channels, 40 timestamped event channels, and three metadata/catalog tables.
- Inspection used DuckDB 1.5.5, `read_only=True`, with external access disabled. SHA-256 of the supplied database was identical before and after detailed inspection.
- Two sample rows per non-metadata table were inspected and saved locally to `.runtime/phase1-samples.json` (ignored by Git). Private telemetry samples and driver/setup values are not committed.
- Database names identify individual sessions, not authoritative race weekends. No alternative schema was observed among the readable files; alternate layouts need synthetic tests, not claims of real-file validation.

## Important columns and inferred mapping

`channelsList(channelName, frequency, unit)` describes regularly sampled tables. They contain `value` or `value1..value4`, without timestamps. `eventsList(eventName, unit)` describes change-event tables with `ts` plus scalar or four-component values. `metadata(key, value)` stores Version, recording/session/track/car context, driver identifiers and a JSON CarSetup value.

| Canonical channel | Observed source | Unit / semantics |
| --- | --- | --- |
| timestamp | GPS Time.value | seconds, 100 Hz recorded clock |
| lap_number | Lap.value with ts | completion count, not a per-sample lap label |
| lap_distance | Lap Dist.value | metres, 10 Hz |
| speed | Ground Speed.value | km/h, 100 Hz; GPS Speed is a separate m/s signal |
| throttle | Throttle Pos.value | percent, 50 Hz; unfiltered input remains a separate channel |
| brake | Brake Pos.value | percent, 50 Hz; unfiltered input remains a separate channel |
| steering | Steering Pos.value | producer unit %, 100 Hz; not steering degrees |
| gear | Gear.value with ts | discrete signed integer |
| rpm | Engine RPM.value | RPM, 100 Hz |
| longitudinal_acceleration | G Force Long.value | G, 10 Hz |
| lateral_acceleration | G Force Lat.value | G, 10 Hz |
| yaw_rate | absent | unknown; do not infer from steering |
| wheel_speeds | Wheel Speed.value1..value4 | m/s, 100 Hz; component order unverified |
| abs | ABS.value with ts | boolean changes |
| tc | TC.value | boolean samples, 100 Hz |
| brake_bias | Brake Bias Rear.value with ts | unit absent; source explicitly says rear, retain that qualifier |
| tyre_wear | Tyres Wear.value1..value4 | producer unit %, 10 Hz |
| tyre_pressure | TyresPressure.value1..value4 | kPa, 10 Hz |
| tyre_temperature | TyresCarcassTemp.value1..value4 | C, 5 Hz; rubber/rim/surface temperatures stay distinct |

## Data-quality findings and proposed adaptations

1. Represent source references with table, value columns, optional timestamp column, sampled/event kind, unit and frequency. An alias map must return missing or ambiguous mappings explicitly; it must not select the first similar name silently. Normalize case/separators only, keeping filtered/unfiltered signals distinct. Inspect unsupported layouts and views structurally without executing view definitions.
2. Reconstruct sampled timestamps only when clock/sample counts and frequency relationships support it. The race clock has 163,906 samples from 0.12 to 1639.445 seconds, including a 0.285-second gap. Row order/frequency alignment is inferred, not recorded in each signal; do not bridge gaps or imply sub-sample precision.
3. The 7 Hz oil/water channels each have 11,503 samples; they do not fit a simple integer stride of the 100 Hz clock. Do not apply the integer-stride reconstruction to them. Full-session raw statistics remain possible; time-local metrics require an independently verified timing model.
4. Lap completion changes run from 0 through 5. The first completion includes pre-race recording time, so its raw boundary interval is not its lap time. The last completion reports zero lap time. Separate reported times from boundary-derived estimates and flag the unclosed final segment.
5. There is a recorded impact change, and finish/pit state changes. These can qualify comparison eligibility, but the file has no explicit lap-validity channel. Return official validity as null; never declare a lap clean from absence of known flags.
6. Last Sector2 is consistent with a cumulative first-plus-second-sector time in this recording. Verify ordering and lap timing before subtracting it to derive individual sector times.
7. Some producer labels merit caution: steering is labelled percent, Brake Thickness is labelled percent despite the name, and LastImpactMagnitude is stored as BOOLEAN. Preserve source types/units and disclose uncertainty rather than fabricating physical quantities.
8. Implement no telemetry resampling, lap-analysis tool, server or launcher during this phase. Phase 1 supplies inspected schema and mapping contracts; Phase 2 organizes the package before the core tools are built.

## Complete observed table inventory

| Table | Columns and types | Rows | Kind | Hz | Producer unit |
| --- | --- | ---: | --- | ---: | --- |
| ABS | ts: DOUBLE, value: BOOLEAN | 3122 | event | - | - |
| ABSLevel | ts: DOUBLE, value: UTINYINT | 1 | event | - | - |
| Ambient Temperature | value: FLOAT | 1640 | sampled | 1 | C |
| AntiStall Activated | ts: DOUBLE, value: BOOLEAN | 1 | event | - | - |
| Best LapTime | ts: DOUBLE, value: FLOAT | 5 | event | - | s |
| Best Sector1 | ts: DOUBLE, value: FLOAT | 5 | event | - | s |
| Best Sector2 | ts: DOUBLE, value: FLOAT | 5 | event | - | s |
| Brake Bias Rear | ts: DOUBLE, value: FLOAT | 1 | event | - | - |
| Brake Migration | ts: DOUBLE, value: FLOAT | 1 | event | - | - |
| Brake Pos | value: FLOAT | 81953 | sampled | 50 | % |
| Brake Pos Unfiltered | value: FLOAT | 81953 | sampled | 50 | % |
| Brake Thickness | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 16391 | sampled | 10 | % |
| Brakes Air Temp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 81953 | sampled | 50 | C |
| Brakes Core Temp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 81953 | sampled | 50 | C |
| Brakes Force | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 81953 | sampled | 50 | % |
| Brakes Temp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 81953 | sampled | 50 | C |
| CloudDarkness | ts: DOUBLE, value: BOOLEAN | 1 | event | - | % |
| Clutch Pos | value: FLOAT | 81953 | sampled | 50 | % |
| Clutch Pos Unfiltered | value: FLOAT | 81953 | sampled | 50 | % |
| Clutch RPM | value: FLOAT | 163906 | sampled | 100 | RPM |
| Current LapTime | ts: DOUBLE, value: FLOAT | 5 | event | - | s |
| Current Sector | ts: DOUBLE, value: UTINYINT | 18 | event | - | - |
| Current Sector1 | ts: DOUBLE, value: FLOAT | 6 | event | - | s |
| Current Sector2 | ts: DOUBLE, value: FLOAT | 6 | event | - | s |
| Engine Max RPM | ts: DOUBLE, value: FLOAT | 1 | event | - | RPM |
| Engine Oil Temp | value: FLOAT | 11503 | sampled | 7 | C |
| Engine RPM | value: FLOAT | 163906 | sampled | 100 | RPM |
| Engine Water Temp | value: FLOAT | 11503 | sampled | 7 | C |
| FFB Output | value: FLOAT | 163906 | sampled | 100 | % |
| Finish Status | ts: DOUBLE, value: UTINYINT | 2 | event | - | - |
| Front3rdDeflection | value: FLOAT | 163906 | sampled | 100 | m |
| FrontFlapActivated | ts: DOUBLE, value: BOOLEAN | 1 | event | - | - |
| FrontRideHeight | value: FLOAT | 163906 | sampled | 100 | m |
| Fuel Level | value: FLOAT | 32782 | sampled | 20 | L |
| FuelMixtureMap | ts: DOUBLE, value: UINTEGER | 1 | event | - | - |
| G Force Lat | value: FLOAT | 16391 | sampled | 10 | G |
| G Force Long | value: FLOAT | 16391 | sampled | 10 | G |
| G Force Vert | value: FLOAT | 16391 | sampled | 10 | G |
| GPS Latitude | value: FLOAT | 16391 | sampled | 10 | deg |
| GPS Longitude | value: FLOAT | 16391 | sampled | 10 | deg |
| GPS Speed | value: FLOAT | 16391 | sampled | 10 | m/s |
| GPS Time | value: DOUBLE | 163906 | sampled | 100 | s |
| Gear | ts: DOUBLE, value: TINYINT | 796 | event | - | - |
| Ground Speed | value: FLOAT | 163906 | sampled | 100 | km/h |
| Headlights State | ts: DOUBLE, value: BOOLEAN | 1 | event | - | On/Off |
| In Pits | ts: DOUBLE, value: UTINYINT | 2 | event | - | - |
| Lap | ts: DOUBLE, value: USMALLINT | 6 | event | - | - |
| Lap Dist | value: FLOAT | 16391 | sampled | 10 | m |
| Lap Time | ts: DOUBLE, value: FLOAT | 6 | event | - | s |
| Last Sector1 | ts: DOUBLE, value: FLOAT | 6 | event | - | s |
| Last Sector2 | ts: DOUBLE, value: FLOAT | 6 | event | - | s |
| LastImpactMagnitude | ts: DOUBLE, value: BOOLEAN | 2 | event | - | - |
| LaunchControlActive | ts: DOUBLE, value: BOOLEAN | 1 | event | - | - |
| Minimum Path Wetness | ts: DOUBLE, value: FLOAT | 1 | event | - | % |
| OffpathWetness | ts: DOUBLE, value: BOOLEAN | 1 | event | - | % |
| OverheatingState | value: BOOLEAN | 3279 | sampled | 2 | - |
| Path Lateral | value: FLOAT | 16391 | sampled | 10 | m |
| Rear3rdDeflection | value: FLOAT | 163906 | sampled | 100 | m |
| RearFlapActivated | ts: DOUBLE, value: BOOLEAN | 1 | event | - | - |
| RearFlapLegalStatus | ts: DOUBLE, value: BOOLEAN | 1 | event | - | - |
| RearRideHeight | value: FLOAT | 163906 | sampled | 100 | m |
| Regen Rate | value: FLOAT | 163906 | sampled | 100 | kW |
| RideHeights | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | m |
| Sector1 Flag | ts: DOUBLE, value: UTINYINT | 3 | event | - | - |
| Sector2 Flag | ts: DOUBLE, value: UTINYINT | 4 | event | - | - |
| Sector3 Flag | ts: DOUBLE, value: UTINYINT | 5 | event | - | - |
| SoC | value: FLOAT | 32782 | sampled | 20 | % |
| Speed Limiter | ts: DOUBLE, value: BOOLEAN | 6 | event | - | - |
| Steering Pos | value: FLOAT | 163906 | sampled | 100 | % |
| Steering Pos Filtered | value: FLOAT | 163906 | sampled | 100 | % |
| Steering Pos Unfiltered | value: FLOAT | 163906 | sampled | 100 | % |
| Steering Shaft Torque | value: FLOAT | 163906 | sampled | 100 | Nm |
| Steering Shaft Torque Unfiltered | value: FLOAT | 16391 | sampled | 10 | Nm |
| SurfaceTypes | value1: UTINYINT, value2: UTINYINT, value3: UTINYINT, value4: UTINYINT | 8196 | sampled | 5 | - |
| Susp Pos | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | m |
| TC | value: BOOLEAN | 163906 | sampled | 100 | - |
| TCCut | ts: DOUBLE, value: UTINYINT | 1 | event | - | - |
| TCLevel | ts: DOUBLE, value: UTINYINT | 1 | event | - | - |
| TCSlipAngle | ts: DOUBLE, value: UTINYINT | 1 | event | - | - |
| Throttle Pos | value: FLOAT | 81953 | sampled | 50 | % |
| Throttle Pos Unfiltered | value: FLOAT | 81953 | sampled | 50 | % |
| Time Behind Next | value: FLOAT | 3279 | sampled | 2 | s |
| Total Dist | value: FLOAT | 16391 | sampled | 10 | m |
| Track Edge | value: FLOAT | 16391 | sampled | 10 | m |
| Track Temperature | value: FLOAT | 1640 | sampled | 1 | C |
| Turbo Boost Pressure | value: FLOAT | 163906 | sampled | 100 | Pa |
| Tyres Wear | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 16391 | sampled | 10 | % |
| TyresCarcassTemp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 8196 | sampled | 5 | C |
| TyresCompound | ts: DOUBLE, value1: UINTEGER, value2: UINTEGER, value3: UINTEGER, value4: UINTEGER | 1 | event | - | - |
| TyresPressure | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 16391 | sampled | 10 | kPa |
| TyresRimTemp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 81953 | sampled | 50 | C |
| TyresRubberTemp | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 16391 | sampled | 10 | C |
| TyresTempCentre | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | C |
| TyresTempLeft | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | C |
| TyresTempRight | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | C |
| Virtual Energy | value: FLOAT | 32782 | sampled | 20 | % |
| Wheel Speed | value1: FLOAT, value2: FLOAT, value3: FLOAT, value4: FLOAT | 163906 | sampled | 100 | m/s |
| WheelsDetached | ts: DOUBLE, value1: UTINYINT, value2: UTINYINT, value3: UTINYINT, value4: UTINYINT | 1 | event | - | - |
| Wind Heading | value: FLOAT | 1640 | sampled | 1 | deg |
| Wind Speed | value: FLOAT | 1640 | sampled | 1 | m/s |
| Yellow Flag State | ts: DOUBLE, value: UTINYINT | 1 | event | - | - |
| channelsList | channelName: VARCHAR, frequency: INTEGER, unit: VARCHAR | 61 | catalog/metadata | - | - |
| eventsList | eventName: VARCHAR, unit: VARCHAR | 40 | catalog/metadata | - | - |
| metadata | key: VARCHAR, value: VARCHAR | 12 | catalog/metadata | - | - |
