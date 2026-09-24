"""Local read-only evidence report for reviewing sourced track ranges."""
import numpy as np
from .alignment import crossing_times
from .analysis.corner_metrics import automatic_ranges
from .database import InspectionError
from .track_knowledge import load_track_knowledge, match_detected_corner

MAX_REPORT_LAPS = 5


def _gps_evidence(session, path, distance):
    names = ('GPS Latitude', 'GPS Longitude')
    if not all(name in session.sources for name in names):
        return None
    try:
        signals = [session.series(name) for name in names]
        if any(signal.unit != 'deg' for signal in signals):
            return None
        timestamp = crossing_times(path, np.asarray([distance], dtype=float), session)[0]
        if not np.isfinite(timestamp):
            return None
        values = [session.sample(name, [timestamp])[0] for name in names]
        if not all(np.isfinite(value) for value in values):
            return None
        return {'latitude_deg': round(float(values[0]), 4),
                'longitude_deg': round(float(values[1]), 4)}
    except InspectionError:
        return None


def build_calibration_report(service, session_id, max_laps=5):
    """Inspect no more than five laps; do not include driver or setup metadata."""
    if type(max_laps) is not int or not 1 <= max_laps <= MAX_REPORT_LAPS:
        raise InspectionError('invalid_lap_limit', 'Use max_laps from 1 to 5.')
    with service.session(session_id) as session:
        track = session.metadata.get('TrackName')
        layout = session.metadata.get('TrackLayout')
        pack = load_track_knowledge(track, layout)
        laps = service._laps(session)
        complete = [lap for lap in laps if lap['complete']]
        selected = sorted(complete, key=lambda lap: (not lap['benchmark_candidate'], lap['lap']))[:max_laps]
        results = []
        unsupported = []
        for lap in selected:
            try:
                path = service._path(session, lap)
                corners, resolution = automatic_ranges(session, lap, path)
                rows = []
                for corner in corners:
                    match = match_detected_corner(corner, pack)
                    rows.append({'detected_corner_id': corner['corner_id'],
                                 'start_distance_m': corner['start_distance_m'],
                                 'apex_distance_m': corner['apex_distance_m'],
                                 'end_distance_m': corner['end_distance_m'],
                                 'entry_speed_kph': corner['entry_speed_kph'],
                                 'minimum_speed_kph': corner['minimum_speed_kph'],
                                 'exit_speed_kph': corner['exit_speed_kph'],
                                 'apex_gps': _gps_evidence(session, path, corner['apex_distance_m']),
                                 'candidate_feature_id': match['feature_id'] if match else None})
                results.append({'lap': lap['lap'], 'benchmark_candidate': lap['benchmark_candidate'],
                                'distance_coverage_m': [float(path[1][0]), float(path[1][-1])],
                                'detection_resolution_m': resolution, 'detected_corners': rows})
            except InspectionError as error:
                unsupported.append({'lap': lap['lap'], 'code': error.code,
                                    'message': str(error)})
        return {'session_id': session_id, 'track': track, 'layout': layout,
                'pack_status': pack['status'] if pack else 'no_pack',
                'pack_features': [{'feature_id': feature['feature_id'], 'name': feature['name'],
                                   'kind': feature['kind'], 'status': feature['status'],
                                   'start_distance_m': feature['start_distance_m'],
                                   'end_distance_m': feature['end_distance_m']}
                                  for feature in pack['features']] if pack else [],
                'considered_laps': len(selected), 'available_laps': len(laps),
                'skipped_incomplete_laps': sum(not lap['complete'] for lap in laps),
                'lap_reports': results, 'unsupported_laps': unsupported,
                'method': 'Automatic steering/lateral-G/speed turn ranges on validated distance paths; optional GPS at minimum-speed apex is rounded to 4 decimals. Candidate names require unique overlap with a reviewed pack. This report does not certify track limits or corner boundaries.'}
