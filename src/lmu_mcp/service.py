"""Direct Python coaching API; database connections live for one request only."""
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import json
import math
import numpy as np
from . import config
from .database import Repository, InspectionError, inspect_connection
from .cache import AnalysisCache
from .telemetry import Session, require
from .analysis.laps import identify_laps, select_lap
from .analysis.summary import lap_summary, speed_factor, control_transitions, match_onsets
from .analysis.braking import BrakingSettings, build_braking_zones, match_positions
from .analysis.corner_metrics import automatic_ranges, corner_metrics
from .manual_corners import load_manual_corners
from .calibration import build_calibration_report
from .track_knowledge import load_track_knowledge, match_detected_corner, match_detected_corners
from .analysis.excursions import ExcursionSettings, detect_path_deviations
from .analysis.history import build_experiments, select_ranked_laps, summarize_corner_evidence
from .setup import parse_car_setup
from dataclasses import asdict
from .alignment import distance_path, make_grid, aligned, validate_grid_request


def _distance_digits(resolution):
    if not isinstance(resolution, (int, float)) or not math.isfinite(resolution):
        return 1
    return min(4, max(1, -Decimal(str(resolution)).as_tuple().exponent))


def serializable(value, field=None, unit=None, distance_digits=1):
    """Round only the wire representation; analysis arrays retain full precision."""
    if isinstance(value, Decimal):
        return serializable(float(value), field, unit, distance_digits)
    if isinstance(value, np.ndarray):
        return serializable(value.tolist(), field, unit, distance_digits)
    if isinstance(value, np.generic):
        return serializable(value.item(), field, unit, distance_digits)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if field in ('resolution_m', 'start_distance_m', 'end_distance_m'):
            digits = 4
        elif (field and field.endswith('_kph')) or (unit == 'km/h' and field not in ('frequency_hz',)):
            digits = 1
        elif (field and field.endswith('_s')) or unit == 's':
            digits = 3
        elif (field and field.endswith('_m')) or unit == 'm':
            digits = distance_digits
        elif unit == '%':
            digits = 3
        elif field and field.endswith('_pct'):
            digits = 1
        else:
            digits = 4
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        own_unit = value.get('unit', unit)
        own_digits = _distance_digits(value['resolution_m']) if 'resolution_m' in value else distance_digits
        units = value.get('units', {})
        result = {}
        for key, item in value.items():
            if key == 'channels' and isinstance(item, dict) and isinstance(units, dict):
                result[key] = {name: serializable(array, name, units.get(name), own_digits)
                               for name, array in item.items()}
            else:
                result[str(key)] = serializable(item, key, own_unit, own_digits)
        return result
    if isinstance(value, (list, tuple)):
        return [serializable(item, field, unit, distance_digits) for item in value]
    return value


def output(value):
    result=serializable(value)
    require(len(json.dumps(result,allow_nan=False).encode('utf-8'))<=config.MAX_OUTPUT_BYTES,
            'response_limit','Response is too large; request fewer channels/laps, a smaller range or coarser resolution.')
    return result


class TelemetryService:
    def __init__(self, repository=None):
        self.repository=repository or Repository()
        self.cache=AnalysisCache()

    @contextmanager
    def session(self, session_id):
        require(isinstance(session_id,str) and 0<len(session_id)<=512,'invalid_session','Use a session ID from list_sessions.')
        with self.repository.open(session_id) as c:
            revision=self.repository.revision(session_id)
            self.cache.activate(session_id,revision)
            inspection_settings=(config.MAX_TABLES,config.MAX_CATALOG_ROWS)
            inspection=self.cache.get(session_id,revision,'inspection',inspection_settings)
            if inspection is None:
                inspection=inspect_connection(c,session_id)
                self.cache.put(session_id,revision,'inspection',inspection,inspection_settings)
            session=Session(c,inspection)
            session.cache_revision=revision
            yield session

    def _laps(self, session):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        rows=self.cache.get(session_id,revision,'laps',settings)
        if rows is None:
            rows=identify_laps(session)
            self.cache.put(session_id,revision,'laps',rows,settings)
        return rows

    def _select_lap(self, session, number):
        return select_lap(session,number,self._laps(session))

    def _path(self, session, lap):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        path=self.cache.get(session_id,revision,'distance_path',lap['lap'],settings)
        if path is None:
            path=distance_path(session,lap)
            self.cache.put(session_id,revision,'distance_path',path,lap['lap'],settings)
        return path

    def _aligned(self, session, lap, path, grid, channels, start, end, resolution):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        parts=(lap['lap'],tuple(channels),start,end,resolution,settings)
        result=self.cache.get(session_id,revision,'aligned',*parts)
        if result is None:
            result=aligned(session,lap,path,grid,channels)
            self.cache.put(session_id,revision,'aligned',result,*parts)
        return result

    def _braking_zones(self, session, lap, settings):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        budget=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        cached=self.cache.get(session_id,revision,'braking_zones',lap['lap'],settings,budget)
        if cached is None:
            cached=build_braking_zones(session,lap,self._path(session,lap),settings)
            self.cache.put(session_id,revision,'braking_zones',cached,lap['lap'],settings,budget)
        return cached

    def get_braking_zones(self, session_id, lap, onset_pct=10.0, release_pct=5.0,
                          min_duration_s=0.3, min_peak_pct=20.0, min_speed_drop_kph=5.0):
        settings=BrakingSettings(onset_pct,release_pct,min_duration_s,min_peak_pct,
                                 min_speed_drop_kph).validate()
        with self.session(session_id) as session:
            selected=self._select_lap(session,lap)
            result=self._braking_zones(session,selected,settings)
            return output({'session_id':session_id,'lap':lap,'lap_quality':selected,
                           'thresholds':asdict(settings),**result,
                           'method':'Native brake samples use onset/release hysteresis; events need minimum duration, peak and speed drop. Distance uses the validated monotonic lap path. No large clock/source gaps are bridged. ABS is positive-state time over covered intervals. Throttle pickup is the first >=5% sample within 5 s and 250 m after release, before the next brake interval. Incomplete onset/release is flagged.'})

    def compare_braking_zones(self, session_id, lap_a, lap_b, onset_pct=10.0,
                              release_pct=5.0, min_duration_s=0.3, min_peak_pct=20.0,
                              min_speed_drop_kph=5.0, max_match_distance_m=100.0):
        settings=BrakingSettings(onset_pct,release_pct,min_duration_s,min_peak_pct,
                                 min_speed_drop_kph).validate()
        require(type(lap_a) is int and type(lap_b) is int and lap_a>0 and lap_b>0 and lap_a!=lap_b,
                'invalid_laps','Choose two distinct positive lap IDs from list_laps.')
        require(type(max_match_distance_m) in (int,float) and math.isfinite(max_match_distance_m)
                and 10<=max_match_distance_m<=300,'invalid_match_range',
                'Use max_match_distance_m from 10 to 300 metres.')
        with self.session(session_id) as session:
            first=self._select_lap(session,lap_a)
            second=self._select_lap(session,lap_b)
            require(first['benchmark_candidate'] and second['benchmark_candidate'],
                    'ineligible_lap','Choose benchmark candidates from list_laps for braking-zone comparison.')
            result_a=self._braking_zones(session,first,settings)
            result_b=self._braking_zones(session,second,settings)
            eligible_a=[z for z in result_a['zones'] if not z['quality_flags']]
            eligible_b=[z for z in result_b['zones'] if not z['quality_flags']]
            pairs,unmatched_a,unmatched_b=match_positions(eligible_a,eligible_b,max_match_distance_m)
            def delta(a,b,key):
                left,right=a[key],b[key]
                return left-right if left is not None and right is not None else None
            matches=[]
            for i,j in pairs:
                a,b=eligible_a[i],eligible_b[j]
                matches.append({'zone_a':a['zone'],'zone_b':b['zone'],
                                'a':a,'b':b,
                                'a_minus_b':{
                                    'brake_start_m':delta(a,b,'start_distance_m'),
                                    'braking_distance_m':delta(a,b,'braking_distance_m'),
                                    'initial_speed_kph':delta(a,b,'initial_speed_kph'),
                                    'minimum_speed_kph':delta(a,b,'minimum_speed_kph'),
                                    'peak_brake_pct':delta(a,b,'peak_brake_pct'),
                                    'brake_release_m':delta(a,b,'end_distance_m'),
                                    'throttle_pickup_m':delta(a,b,'throttle_pickup_distance_m'),
                                    'abs_active_time_s':delta(a,b,'abs_active_time_s')}})
            return output({'session_id':session_id,'lap_a':lap_a,'lap_b':lap_b,
                           'thresholds':asdict(settings),'max_match_distance_m':max_match_distance_m,
                           'matches':matches,'unmatched_zone_ids_a':[eligible_a[i]['zone'] for i in unmatched_a],
                           'unmatched_zone_ids_b':[eligible_b[j]['zone'] for j in unmatched_b],
                           'excluded_partial_zone_ids_a':[z['zone'] for z in result_a['zones'] if z['quality_flags']],
                           'excluded_partial_zone_ids_b':[z['zone'] for z in result_b['zones'] if z['quality_flags']],
                           'excluded_intervals_a':result_a['excluded_intervals'],
                           'excluded_intervals_b':result_b['excluded_intervals'],
                           'warnings_a':result_a['warnings'],'warnings_b':result_b['warnings'],
                           'note':'Matches maximize count then minimize start-position distance without crossing zone order. A-minus-B is first lap minus second in stated units. Unmatched or partial zones are not silently paired; measured differences do not establish a driving cause.'})

    def _corners(self, session, lap):
        manual=load_manual_corners(session.metadata.get('TrackName'),
                                   session.metadata.get('TrackLayout'))
        pack=(load_track_knowledge(session.metadata.get('TrackName'),
                                   session.metadata.get('TrackLayout'))
              if manual is None else None)
        definition_key=json.dumps({'manual':manual,'pack':pack},sort_keys=True)
        session_id=session.inspection.session_id
        revision=session.cache_revision
        budget=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        cached=self.cache.get(session_id,revision,'corners',lap['lap'],definition_key,budget)
        if cached is None:
            path=self._path(session,lap)
            if manual is not None:
                ranges=manual
                spacing=None
                source='manual'
            else:
                ranges,spacing=automatic_ranges(session,lap,path)
                source='automatic'
            rows=[corner_metrics(session,lap,path,row) for row in ranges]
            if pack is not None:
                sources={item['id']:item for item in pack['sources']}
                for row,feature in zip(rows,match_detected_corners(rows,pack)):
                    if feature is not None:
                        row['name']=feature['name']
                        row['track_feature']={
                            'feature_id':feature['feature_id'],
                            'status':feature['status'],
                            'uncertainty_m':feature['uncertainty_m'],
                            'distance_method':feature['distance_method'],
                            'character':feature['character'],
                            'sources':[sources[source_id] for source_id in feature['source_ids']]}
            cached={'corners':rows,'definition_source':source,
                    'automatic_resolution_m':spacing,
                    'method':'User manual definitions override automatic detection and curated names. Curated names attach only to uniquely overlapping measured ranges; their calibration status and sources are explicit. Automatic ranges require sustained steering percent and lateral G; minimum speed estimates the apex. Section timing and controls are approximate; null or quality flags mean unsupported coverage.'}
            self.cache.put(session_id,revision,'corners',cached,lap['lap'],definition_key,budget)
        return cached

    def get_corners(self, session_id, lap, offset=0, limit=50):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=50,
                'invalid_page','Use offset >= 0 and limit from 1 to 50 for corners.')
        with self.session(session_id) as session:
            selected=self._select_lap(session,lap)
            result=self._corners(session,selected)
            rows=result['corners']
            return output({'session_id':session_id,'lap':lap,'lap_quality':selected,
                           'corners':rows[offset:offset+limit],
                           'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,
                           'definition_source':result['definition_source'],
                           'automatic_resolution_m':result['automatic_resolution_m'],
                           'units':{'distance':'m','speed':'km/h','time':'s','steering':'%'},
                           'method':result['method']})

    def compare_corner(self, session_id, corner_id, laps):
        require(type(corner_id) is int and 1<=corner_id<=1000,'invalid_corner',
                'Choose a positive corner_id from get_corners on the first lap.')
        require(isinstance(laps,list) and all(type(n) is int and n>0 for n in laps)
                and 2<=len(laps)<=5 and len(set(laps))==len(laps),
                'invalid_laps','Compare 2 to 5 distinct positive benchmark-candidate lap IDs.')
        with self.session(session_id) as session:
            selected=[self._select_lap(session,n) for n in laps]
            require(all(lap['benchmark_candidate'] for lap in selected),
                    'ineligible_lap','Choose benchmark candidates from list_laps for corner comparison.')
            reference_result=self._corners(session,selected[0])
            reference=next((row for row in reference_result['corners'] if row['corner_id']==corner_id),None)
            require(reference is not None,'unknown_corner',
                    'Corner ID is not present on the first lap; call get_corners for that lap.')
            compared=[]
            unmatched=[]
            keys=('brake_point_m','turn_in_position_m','apex_distance_m',
                  'minimum_speed_position_m','minimum_speed_kph',
                  'throttle_pickup_position_m','full_throttle_position_m',
                  'entry_speed_kph','exit_speed_kph','section_time_s',
                  'abs_active_time_s','tc_active_time_s',
                  'maximum_absolute_steering_pct','mean_absolute_steering_pct')
            for lap in selected[1:]:
                result=self._corners(session,lap)
                if reference_result['definition_source']=='manual':
                    candidate=next((row for row in result['corners'] if row['corner_id']==corner_id),None)
                    match_method='manual_id'
                else:
                    choices=[row for row in result['corners']
                             if abs(row['start_distance_m']-reference['start_distance_m'])<=100]
                    choices.sort(key=lambda row:(abs(row['start_distance_m']-reference['start_distance_m']),
                                                 row['start_distance_m']))
                    candidate=choices[0] if choices else None
                    match_method='nearest_start_within_100_m'
                if candidate is None:
                    unmatched.append(lap['lap'])
                    continue
                differences={key:(candidate[key]-reference[key]
                                  if candidate.get(key) is not None and reference.get(key) is not None else None)
                             for key in keys}
                if candidate['quality_flags'] or reference['quality_flags']:
                    differences={key:None for key in keys}
                compared.append({'lap':lap['lap'],'corner':candidate,
                                 'match_method':match_method,
                                 'start_match_distance_m':abs(candidate['start_distance_m']-reference['start_distance_m']),
                                 'lap_minus_reference':differences})
            return output({'session_id':session_id,'corner_id':corner_id,
                           'reference_lap':laps[0],'reference_corner':reference,
                           'comparisons':compared,'unmatched_laps':unmatched,
                           'definition_source':reference_result['definition_source'],
                           'units':{'distance':'m','speed':'km/h','time':'s','steering':'%'},
                           'note':'Automatic corner IDs are per-lap ordinals; later laps match the first lap by approximate start position within 100 m. Manual IDs match exact track/layout definitions. Deltas are lap minus reference in each field unit; quality flags suppress unsupported deltas. Section time is reconstructed, not official. Differences alone do not establish driving cause.'})

    def _excursion_lap(self, session, lap):
        # Validate the complete lap path first; never sort or repair reversals.
        self._path(session, lap)
        lateral = session.series("path_lateral")
        edge = session.series("track_edge")
        distance = session.series("lap_distance")
        require(
            lateral.unit == edge.unit == distance.unit == "m",
            "unknown_excursion_unit",
            "Excursion analysis requires verified metre units for Path Lateral, Track Edge and lap distance.",
        )
        mask = (lateral.times >= lap["start_s"]) & (lateral.times < lap["end_s"])
        times = lateral.times[mask]
        require(
            len(times) >= 2,
            "unsupported_excursion_signals",
            "Complete lap has insufficient Path Lateral observations.",
        )
        result = detect_path_deviations(
            times,
            session.sample("lap_distance", times),
            lateral.values[mask],
            session.sample("track_edge", times),
            min(lateral.max_gap_s, edge.max_gap_s, distance.max_gap_s),
            ExcursionSettings(),
        )
        result["observed_duration_s"] = float(lap["end_s"] - lap["start_s"])
        result["coverage_fraction"] = (
            result["coverage_s"] / result["observed_duration_s"]
            if result["observed_duration_s"] > 0 else 0.0
        )
        return result

    def _excursion_session(self, session_id, remaining_laps):
        with self.session(session_id) as session:
            laps = self._laps(session)
            complete = [lap for lap in laps if lap["complete"]]
            summary = {
                "session_id": session_id,
                "complete_laps": len(complete),
                "partial_laps_excluded": sum(not lap["complete"] for lap in laps),
                "analyzed_laps": 0,
                "flagged_complete_laps": 0,
                "unsupported_laps": [],
            }
            events = []
            coverage_s = observed_s = 0.0
            selected = complete[:remaining_laps]
            for lap in selected:
                try:
                    result = self._excursion_lap(session, lap)
                except InspectionError as error:
                    summary["unsupported_laps"].append({"lap": lap["lap"], "code": error.code})
                    continue
                summary["analyzed_laps"] += 1
                summary["flagged_complete_laps"] += int(bool(lap["flags"]))
                coverage_s += result["coverage_s"]
                observed_s += result["observed_duration_s"]
                for event in result["events"]:
                    events.append({**event, "session_id": session_id, "lap": lap["lap"],
                                   "lap_flags": list(lap["flags"])})
            summary["complete_laps_truncated"] = len(complete) > len(selected)
            summary["coverage_s"] = coverage_s
            summary["observed_duration_s"] = observed_s
            return session.metadata, summary, events

    @staticmethod
    def _excursion_hotspots(events, pack):
        clusters = []
        for event in sorted(events, key=lambda item: (item["side"], item["peak_distance_m"])):
            cluster = next((item for item in reversed(clusters)
                            if item["side"] == event["side"]
                            and event["peak_distance_m"] - item["last_peak_m"] <= 100), None)
            if cluster is None:
                cluster = {"side": event["side"], "events": [],
                           "last_peak_m": event["peak_distance_m"]}
                clusters.append(cluster)
            cluster["events"].append(event)
            cluster["last_peak_m"] = event["peak_distance_m"]
        rows = []
        for cluster in clusters:
            items = cluster["events"]
            laps = {(item["session_id"], item["lap"]) for item in items}
            sessions = {item["session_id"] for item in items}
            start = min(item["start_distance_m"] for item in items)
            end = max(item["end_distance_m"] for item in items)
            feature = match_detected_corner(
                {"start_distance_m": start, "end_distance_m": end}, pack
            ) if pack else None
            examples = [{"session_id": sid, "lap": lap} for sid, lap in sorted(laps)[:5]]
            rows.append({
                "side": cluster["side"],
                "start_distance_m": start,
                "end_distance_m": end,
                "peak_distance_m": sum(item["peak_distance_m"] for item in items) / len(items),
                "maximum_excess_m": max(item["peak_excess_m"] for item in items),
                "event_count": len(items),
                "distinct_affected_laps": len(laps),
                "distinct_affected_sessions": len(sessions),
                "affected_lap_examples": examples,
                "affected_lap_examples_truncated": len(laps) > len(examples),
                "confidence": "unconfirmed_repeated" if len(laps) >= 2 else "unconfirmed_single",
                "track_feature": ({"feature_id": feature["feature_id"], "name": feature["name"],
                                   "status": feature["status"], "uncertainty_m": feature["uncertainty_m"]}
                                  if feature else None),
            })
        rows.sort(key=lambda item: (-item["distinct_affected_laps"], -item["event_count"],
                                    item["start_distance_m"], item["side"]))
        for index, row in enumerate(rows, 1):
            row["hotspot_id"] = index
        return rows

    def get_excursion_hotspots(self, session_id, scope="recent", offset=0, limit=50):
        require(scope in ("recent", "general"), "invalid_scope",
                "Use scope 'recent' for the selected recording or 'general' for bounded exact-layout/car history.")
        require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 50,
                "invalid_page", "Use offset >= 0 and limit from 1 to 50 for excursion hotspots.")
        with self.session(session_id) as selected_session:
            identity = {key: selected_session.metadata.get(key)
                        for key in ("TrackName", "TrackLayout", "CarName")}
        require(all(isinstance(value, str) and value for value in identity.values()),
                "missing_identity", "Track, layout and car metadata are required for excursion history.")
        session_ids = [session_id]
        candidates_examined = 0
        sessions_truncated = False
        if scope == "general":
            discovered = sorted(self.repository.discover(),
                                key=lambda item: (item.get("modified_ns", 0), item["session_id"]),
                                reverse=True)
            for item in discovered:
                candidate = item["session_id"]
                if candidate == session_id or item.get("status") != "discovered":
                    continue
                if candidates_examined >= config.MAX_EXCURSION_DISCOVERY_CANDIDATES:
                    sessions_truncated = True
                    break
                candidates_examined += 1
                try:
                    with self.session(candidate) as other:
                        matches = all(other.metadata.get(key) == value for key, value in identity.items())
                except InspectionError:
                    continue
                if matches:
                    if len(session_ids) >= config.MAX_EXCURSION_HISTORY_SESSIONS:
                        sessions_truncated = True
                        break
                    session_ids.append(candidate)
        events = []
        summaries = []
        remaining = config.MAX_EXCURSION_HISTORY_LAPS
        laps_truncated = False
        for current in session_ids:
            if remaining <= 0:
                laps_truncated = True
                break
            _, summary, found = self._excursion_session(current, remaining)
            summaries.append(summary)
            used = min(summary["complete_laps"], remaining)
            remaining -= used
            laps_truncated |= summary["complete_laps_truncated"]
            events.extend(found)
        pack = load_track_knowledge(identity["TrackName"], identity["TrackLayout"])
        hotspots = self._excursion_hotspots(events, pack)
        analyzed_laps = sum(item["analyzed_laps"] for item in summaries)
        coverage_s = sum(item["coverage_s"] for item in summaries)
        observed_s = sum(item["observed_duration_s"] for item in summaries)
        unsupported_count = sum(len(item["unsupported_laps"]) for item in summaries)
        status = "unsupported" if analyzed_laps == 0 else ("partial" if unsupported_count else "supported")
        return output({
            "session_id": session_id,
            "scope": scope,
            "identity": identity,
            "status": status,
            "hotspots": hotspots[offset:offset + limit],
            "total": len(hotspots),
            "next_offset": offset + limit if offset + limit < len(hotspots) else None,
            "event_count": len(events),
            "distinct_affected_laps": len({(event["session_id"], event["lap"]) for event in events}),
            "distinct_affected_sessions": len({event["session_id"] for event in events}),
            "sessions": summaries,
            "coverage": {"analyzed_laps": analyzed_laps, "coverage_s": coverage_s,
                         "observed_duration_s": observed_s,
                         "fraction": coverage_s / observed_s if observed_s > 0 else 0.0},
            "confidence": "unconfirmed_path_deviation",
            "truncation": {
                "candidate_sessions_examined": candidates_examined,
                "candidate_session_limit": config.MAX_EXCURSION_DISCOVERY_CANDIDATES,
                "matching_session_limit": config.MAX_EXCURSION_HISTORY_SESSIONS,
                "complete_lap_limit": config.MAX_EXCURSION_HISTORY_LAPS,
                "sessions_truncated": sessions_truncated,
                "laps_truncated": laps_truncated,
                "page_truncated": offset + limit < len(hotspots),
            },
            "corroboration": {
                "surface_types": "not_used: component-to-wheel/current-build semantics unverified",
                "gps": "not_used: no sourced circuit-boundary polygon",
            },
            "units": {"distance": "m", "time": "s"},
            "method": "Complete laps, including flagged laps, are counted without becoming pace benchmarks. Sustained vehicle-centre Path Lateral magnitude beyond same-side Track Edge is clustered within 100 m by side. Missing data, clock/source gaps, lap resets and invalid distance paths are not bridged. Results are unconfirmed path deviations, not official track-limit violations.",
        })
    def _bounded_history_sessions(self, session_id, scope):
        with self.session(session_id) as selected_session:
            identity = {key: selected_session.metadata.get(key)
                        for key in ("TrackName", "TrackLayout", "CarName")}
        require(all(isinstance(value, str) and value for value in identity.values()),
                "missing_identity", "Track, layout and car metadata are required for history analysis.")
        session_ids = [session_id]
        examined = 0
        truncated = False
        if scope == "general":
            discovered = sorted(self.repository.discover(),
                                key=lambda item: (item.get("modified_ns", 0), item["session_id"]),
                                reverse=True)
            for item in discovered:
                candidate = item["session_id"]
                if candidate == session_id or item.get("status") != "discovered":
                    continue
                if examined >= config.MAX_EXCURSION_DISCOVERY_CANDIDATES:
                    truncated = True
                    break
                examined += 1
                try:
                    with self.session(candidate) as other:
                        matches = all(other.metadata.get(key) == value
                                      for key, value in identity.items())
                except InspectionError:
                    continue
                if matches:
                    if len(session_ids) >= config.MAX_EXCURSION_HISTORY_SESSIONS:
                        truncated = True
                        break
                    session_ids.append(candidate)
        return identity, session_ids, examined, truncated

    @staticmethod
    def _match_history_corner(reference, reference_source, rows):
        if reference_source == "manual":
            return next((row for row in rows
                         if row["corner_id"] == reference["corner_id"]), None), "manual_id"
        feature = reference.get("track_feature")
        if feature:
            candidate = next((row for row in rows
                              if row.get("track_feature", {}).get("feature_id") == feature["feature_id"]), None)
            if candidate:
                return candidate, "sourced_feature_id"
        choices = [row for row in rows
                   if abs(row["start_distance_m"] - reference["start_distance_m"]) <= 100]
        choices.sort(key=lambda row: (abs(row["start_distance_m"] - reference["start_distance_m"]),
                                      row["start_distance_m"]))
        return (choices[0], "nearest_start_within_100_m") if choices else (None, "unmatched")

    def get_corner_history(self, session_id, corner_id, scope="recent"):
        require(type(corner_id) is int and 1 <= corner_id <= 1000, "invalid_corner",
                "Choose a positive corner_id from get_corners on a complete reference lap.")
        require(scope in ("recent", "general"), "invalid_scope",
                "Use scope 'recent' for the selected recording or 'general' for bounded exact-layout/car history.")
        identity, session_ids, candidates_examined, sessions_truncated = self._bounded_history_sessions(
            session_id, scope
        )
        candidates = []
        conditions = []
        unsupported_laps = []
        remaining = config.MAX_EXCURSION_HISTORY_LAPS
        laps_truncated = False
        for current in session_ids:
            if remaining <= 0:
                laps_truncated = True
                break
            with self.session(current) as session:
                laps = self._laps(session)
                complete = [lap for lap in laps if lap["complete"]]
                chosen = complete[:remaining]
                remaining -= len(chosen)
                laps_truncated |= len(complete) > len(chosen)
                valid_laps = []
                for lap in chosen:
                    distance_valid = True
                    try:
                        self._path(session, lap)
                    except InspectionError as error:
                        distance_valid = False
                        unsupported_laps.append({"session_id": current, "lap": lap["lap"],
                                                 "code": error.code})
                    candidate = {
                        "session_id": current,
                        "lap": lap["lap"],
                        "lap_time_s": lap["lap_time_s"],
                        "benchmark_candidate": lap["benchmark_candidate"],
                        "complete": True,
                        "distance_valid": distance_valid,
                        "flags": list(lap["flags"]),
                    }
                    candidates.append(candidate)
                    if distance_valid:
                        valid_laps.append(lap)
                conditions.append({
                    "session_id": current,
                    "weather": session.metadata.get("WeatherConditions"),
                    "session_type": session.metadata.get("SessionType"),
                    "complete_laps_considered": len(chosen),
                    "distance_valid_laps": len(valid_laps),
                })
        selected_valid = [row for row in candidates
                          if row["session_id"] == session_id and row["distance_valid"]]
        require(selected_valid, "unsupported_corner_history",
                "Selected recording has no complete distance-valid lap for resolving corner_id.")
        reference_candidate = min(
            selected_valid,
            key=lambda row: (not row["benchmark_candidate"],
                             row["lap_time_s"] if type(row["lap_time_s"]) in (int, float)
                             and row["lap_time_s"] > 0 else float("inf"), row["lap"]),
        )
        with self.session(session_id) as session:
            reference_lap = self._select_lap(session, reference_candidate["lap"])
            reference_result = self._corners(session, reference_lap)
            reference = next((row for row in reference_result["corners"]
                              if row["corner_id"] == corner_id), None)
            require(reference is not None, "unknown_corner",
                    "Corner ID is absent on the selected recording's resolved reference lap; call get_corners for a complete lap.")
            setup = parse_car_setup(session.reader.car_setup_json())
        ranking = select_ranked_laps(candidates)
        sample_rows = []
        unmatched = []
        overlap_events = 0
        overlap_laps = set()
        selected_by_session = {}
        for row in ranking["selected"]:
            selected_by_session.setdefault(row["session_id"], []).append(row)
        metric_fields = tuple(field for fields in (
            ("entry_speed_kph", "brake_point_m", "turn_in_position_m"),
            ("minimum_speed_kph", "minimum_speed_position_m", "maximum_absolute_steering_pct"),
            ("throttle_pickup_position_m", "full_throttle_position_m", "exit_speed_kph", "tc_active_time_s"),
        ) for field in fields)
        for current, selected_rows in selected_by_session.items():
            with self.session(current) as session:
                laps = {lap["lap"]: lap for lap in self._laps(session)}
                for selected in selected_rows:
                    lap = laps[selected["lap"]]
                    result = self._corners(session, lap)
                    corner, match_method = self._match_history_corner(
                        reference, reference_result["definition_source"], result["corners"]
                    )
                    if corner is None:
                        unmatched.append({"session_id": current, "lap": lap["lap"]})
                        continue
                    try:
                        excursion = self._excursion_lap(session, lap)
                        overlaps = [event for event in excursion["events"]
                                    if event["end_distance_m"] >= corner["start_distance_m"]
                                    and event["start_distance_m"] <= corner["end_distance_m"]]
                    except InspectionError:
                        overlaps = []
                    if overlaps:
                        overlap_events += len(overlaps)
                        overlap_laps.add((current, lap["lap"]))
                    metrics = {field: corner.get(field) for field in metric_fields}
                    sample_rows.append({
                        "session_id": current,
                        "lap": lap["lap"],
                        "selection": selected["selection"],
                        "lap_time_s": selected["lap_time_s"],
                        "timing_source": selected["timing_source"],
                        "benchmark_candidate": selected["benchmark_candidate"],
                        "quality_flags": list(corner.get("quality_flags", [])),
                        "lap_flags": list(selected["flags"]),
                        "match_method": match_method,
                        "metrics": metrics,
                        "excursion_overlap_count": len(overlaps),
                    })
        evidence = summarize_corner_evidence(sample_rows)
        relevant_ids = {
            "VM_BRAKE_BALANCE", "VM_BRAKE_PRESSURE", "VM_FRONT_WING", "VM_REAR_WING",
            "VM_DIFF_PRELOAD", "VM_DIFF_POWER", "VM_DIFF_COAST", "VM_FRONT_ANTISWAY",
            "VM_REAR_ANTISWAY", "VM_TRACTIONCONTROLMAP",
            "VM_TRACTIONCONTROLPOWERCUTMAP", "VM_TRACTIONCONTROLSLIPANGLEMAP",
        }
        relevant_settings = [row for row in setup["settings"]
                             if row["setting_id"] in relevant_ids]
        coaching = build_experiments(evidence, identity["CarName"], relevant_settings)
        weather_values = {row["weather"] for row in conditions if row["weather"] is not None}
        return output({
            "session_id": session_id,
            "corner_id": corner_id,
            "scope": scope,
            "identity": identity,
            "status": "supported" if sample_rows else ranking["status"],
            "reference": {
                "session_id": session_id,
                "lap": reference_lap["lap"],
                "corner_id": reference["corner_id"],
                "name": reference.get("name"),
                "start_distance_m": reference["start_distance_m"],
                "end_distance_m": reference["end_distance_m"],
                "definition_source": reference_result["definition_source"],
                "track_feature": reference.get("track_feature"),
            },
            "selection": {**{key: value for key, value in ranking.items() if key != "selected"},
                          "laps": ranking["selected"]},
            "lap_samples": sample_rows,
            "evidence": evidence,
            "unmatched_laps": unmatched,
            "unsupported_laps": unsupported_laps,
            "excursion_overlap": {
                "event_count": overlap_events,
                "affected_laps": len(overlap_laps),
                "confidence": "unconfirmed_path_deviation",
            },
            "conditions": {
                "sessions": conditions,
                "mixed_weather": len(weather_values) > 1,
                "note": "Weather/session metadata is recording-level context; traffic and changing grip remain unmeasured confounders.",
            },
            "setup_context": {
                "status": setup["status"],
                "settings": relevant_settings,
                "omitted": setup["omitted"],
                "warnings": setup["warnings"],
                "note": "Recorded current context only. Raw integer direction is unverified unless an experiment cites an exact applicable car source; no setup file is written.",
            },
            "experiments": coaching["experiments"],
            "feedback_requests": coaching["feedback_requests"],
            "next_step": coaching["next_step"],
            "sources": coaching["sources"],
            "truncation": {
                "candidate_sessions_examined": candidates_examined,
                "candidate_session_limit": config.MAX_EXCURSION_DISCOVERY_CANDIDATES,
                "matching_session_limit": config.MAX_EXCURSION_HISTORY_SESSIONS,
                "complete_lap_limit": config.MAX_EXCURSION_HISTORY_LAPS,
                "sessions_truncated": sessions_truncated,
                "laps_truncated": laps_truncated,
            },
            "units": {"distance": "m", "speed": "km/h", "time": "s", "steering": "%"},
            "method": "Recorded Lap Time ranks disjoint fastest benchmark and slowest complete distance-valid groups. Corner matching uses manual ID, then unique sourced feature, then nearest measured start within 100 m. Repeated entry/mid/exit differences are observations, not causes. Setup experiments require repeated evidence, an available allowlisted setting and an exact car-applicable source; change one setting at a time.",
        })
    def get_track_guide(self, session_id, offset=0, limit=50):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=50,
                'invalid_page','Use offset >= 0 and limit from 1 to 50 for track features.')
        with self.session(session_id) as session:
            track=session.metadata.get('TrackName')
            layout=session.metadata.get('TrackLayout')
            pack=load_track_knowledge(track,layout)
            features=pack['features'] if pack else []
            return output({'session_id':session_id,'track':track,'layout':layout,
                           'pack_status':pack['status'] if pack else 'no_pack',
                           'sources':pack['sources'] if pack else [],
                           'coaching':pack.get('coaching',[]) if pack else [],
                           'features':features[offset:offset+limit],
                           'total':len(features),
                           'next_offset':offset+limit if offset+limit<len(features) else None,
                           'units':{'distance':'m'},
                           'note':'Names and character are sourced; coaching notes label evidence and applicability. Distances carry calibration status and uncertainty, not braking targets. This guide does not establish a measured driving cause.'})

    def calibration_report(self, session_id, max_laps=5):
        return output(build_calibration_report(self, session_id, max_laps))

    def list_sessions(self, search='', offset=0, limit=20):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'invalid_page','Use a nonnegative offset and limit from 1 to 100.')
        require(isinstance(search,str) and len(search)<=128,'invalid_search','Search must be at most 128 characters.')
        rows=[row for row in self.repository.discover() if search.casefold() in row['session_id'].casefold()]
        rows.sort(key=lambda r:(r.get('modified_ns',0),r['session_id']),reverse=True)
        selected=[]
        for row in rows[offset:offset+limit]:
            selected.append({'session_id':row['session_id'],'filename':Path(row['session_id']).name,
                             'modified_at':datetime.fromtimestamp(row['modified_ns']/1e9,timezone.utc).isoformat() if 'modified_ns' in row else None,
                             'size_bytes':row.get('size_bytes'),'status':row['status']})
        return output({'sessions':selected,'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None})

    def get_session_info(self, session_id):
        with self.session(session_id) as s:
            warnings=list(s.inspection.warnings)
            duration=None;laps=None
            try: duration=float(s.clock[-1]-s.clock[0]);laps=self._laps(s)
            except InspectionError as e: warnings.append(e.code+': '+str(e))
            return output({'session_id':session_id,'car':s.metadata.get('CarName'),'car_class':s.metadata.get('CarClass'),
                           'track':s.metadata.get('TrackName'),'track_layout':s.metadata.get('TrackLayout'),
                           'session_type':s.metadata.get('SessionType'),'start_time':s.metadata.get('RecordingTime'),
                           'weather':s.metadata.get('WeatherConditions'),'session_duration_s':duration,
                           'number_of_laps':sum(r['complete'] for r in laps) if laps is not None else None,
                           'recorded_intervals':len(laps) if laps is not None else None,
                           'available_channels':list(s.sources),'sample_rates_hz':sorted({v['frequency_hz'] for v in s.inspection.catalog.values() if v['frequency_hz']}),
                           'database_tables':[{'schema':t.schema,'table':t.name,'kind':t.kind,'rows':t.row_count} for t in s.inspection.tables],
                           'warnings':warnings,'validity_note':'Official validity is unavailable; benchmark eligibility is a separate heuristic.'})

    def list_channels(self, session_id):
        with self.session(session_id) as s:
            rows=[]
            for name,source in s.sources.items():
                table=next(t for t in s.inspection.tables if (t.schema,t.name)==(source.schema,source.table))
                rows.append({'name':name,'source':source.table,'source_columns':list(source.value_columns),
                             'timestamp_column':source.timestamp_column,'unit':source.unit,'frequency_hz':source.frequency_hz,
                             'sample_count':table.row_count,'kind':source.kind,'extrema':s.reader.extrema(source)})
            return output({'channels':rows,'missing_canonical_channels':s.inspection.channels.missing,
                           'ambiguous_canonical_channels':list(s.inspection.channels.ambiguous),
                           'component_syntax':'Use name:value1 for multi-component channels; wheel order is unverified.',
                           'warnings':s.inspection.warnings})

    def list_laps(self, session_id, offset=0, limit=50):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'invalid_page','Use offset >=0 and limit 1..100.')
        with self.session(session_id) as s:
            laps=self._laps(s)
            speed=None;factor=None
            try: speed=s.series('speed');factor=speed_factor(speed.unit)
            except InspectionError: pass
            rows=[]
            for lap in laps[offset:offset+limit]:
                inside=(s.clock>=lap['start_s'])&(s.clock<lap['end_s'])
                values=speed.values[(speed.times>=lap['start_s'])&(speed.times<lap['end_s'])] if speed is not None else np.array([])
                values=values[np.isfinite(values)]
                rows.append({**lap,'sample_count':int(inside.sum()),'max_speed_kph':float(values.max()*factor) if len(values) and factor else None})
            return output({'laps':rows,'total':len(laps),'next_offset':offset+limit if offset+limit<len(laps) else None,
                           'lap_id_note':'lap is a unique interval ID in recording order; recorded_lap_number is the producer completion counter. Partial intervals are retained.'})

    def get_lap_summary(self, session_id, lap):
        with self.session(session_id) as s: return output(lap_summary(s,self._select_lap(s,lap)))

    def get_telemetry(self, session_id, lap, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=2.0):
        channels=['speed','brake','throttle','steering','gear'] if channels is None else channels
        validate_grid_request(start_distance_m,end_distance_m,resolution_m,channels)
        with self.session(session_id) as s:
            info=self._select_lap(s,lap);path=self._path(s,info)
            end=float(path[1][-1]) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels)
            result=self._aligned(s,info,path,grid,channels,start_distance_m,end,resolution_m)
            return output({**result,'start_distance_m':start_distance_m,'end_distance_m':end,'resolution_m':resolution_m,
                           'distance_m':grid,'lap_quality':info,'note':'No extrapolation: uncovered distance or timing gaps return null. Units remain producer units; steering is not converted to degrees.'})

    def compare_laps(self, session_id, laps, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=20.0):
        require(isinstance(laps,list) and all(type(n) is int for n in laps) and 2<=len(laps)<=config.MAX_LAPS_PER_REQUEST and len(set(laps))==len(laps),
                'invalid_laps','Compare 2 to 10 distinct lap IDs.')
        channels=['speed','brake','throttle','steering'] if channels is None else channels
        validate_grid_request(start_distance_m,end_distance_m,resolution_m,channels,len(laps))
        with self.session(session_id) as s:
            infos=[self._select_lap(s,n) for n in laps]
            require(all(r['benchmark_candidate'] for r in infos),'ineligible_lap','Choose benchmark candidates from list_laps; comparisons exclude incomplete, zero-time, pit, impact and clock-gap intervals.')
            paths=[self._path(s,r) for r in infos]
            end=min(float(path[1][-1]) for path in paths) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels,len(laps))
            results=[self._aligned(s,r,path,grid,channels,start_distance_m,end,resolution_m) for r,path in zip(infos,paths)]
            deltas=[]
            for i in range(1,len(results)):
                a,b=results[0],results[i]
                speed_delta=None
                if 'speed' in channels:
                    factor=speed_factor(a['units']['speed'])
                    if factor is not None: speed_delta=(a['channels']['speed']-b['channels']['speed'])*factor
                deltas.append({'lap_a':laps[0],'lap_b':laps[i],'elapsed_delta_a_minus_b_s':a['elapsed_s']-b['elapsed_s'],
                               'speed_delta_a_minus_b_kph':speed_delta,'reported_lap_delta_s':infos[0]['lap_time_s']-infos[i]['lap_time_s']})
            transitions=[control_transitions(s,r,p,start_distance_m,end) for r,p in zip(infos,paths)]
            return output({'distance_m':grid,'resolution_m':resolution_m,'laps':results,'deltas':deltas,
                           'control_onsets':[{'lap':n,**v} for n,v in zip(laps,transitions)],
                           'control_point_differences':[{'lap_a':laps[0],'lap_b':laps[i],**match_onsets(transitions[0],transitions[i])} for i in range(1,len(laps))],
                           'method':'Delta = lap A elapsed time minus B at shared distance crossings; positive means A is slower. Crossing times are interpolated, not official timing deltas. Control onsets are first samples at >=5%, coarsely matched one-to-one within 100 m, not named corners or braking zones. Positive onset-distance difference means A applies the control later along the track.',
                           'conditions':'Same recording/car/layout; fuel, tyres, weather and traffic can still differ. See get_lap_summary condition_context. Official lap validity is unknown.'})
