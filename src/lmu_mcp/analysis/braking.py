"""Time-domain braking intervals and ordered distance matching."""
from dataclasses import dataclass
import math
import numpy as np

from ..telemetry import require
from ..database import InspectionError


@dataclass(frozen=True)
class BrakingSettings:
    onset_pct: float = 10.0
    release_pct: float = 5.0
    min_duration_s: float = 0.3
    min_peak_pct: float = 20.0
    min_speed_drop_kph: float = 5.0

    def validate(self):
        values = (self.onset_pct, self.release_pct, self.min_duration_s,
                  self.min_peak_pct, self.min_speed_drop_kph)
        require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in values), 'invalid_threshold', 'Braking thresholds must be finite numbers.')
        require(1 <= self.onset_pct <= 100 and 0 <= self.release_pct < self.onset_pct
                and self.onset_pct <= self.min_peak_pct <= 100,
                'invalid_threshold', 'Use 1 <= onset_pct <= min_peak_pct <= 100 and 0 <= release_pct < onset_pct.')
        require(0.1 <= self.min_duration_s <= 10 and 0 <= self.min_speed_drop_kph <= 150,
                'invalid_threshold', 'Use min_duration_s from 0.1 to 10 and min_speed_drop_kph from 0 to 150.')
        return self


def detect_intervals(times, brake_pct, max_gap_s, settings: BrakingSettings):
    """Hysteresis: enter at onset, leave below release; never bridge invalid samples/gaps."""
    settings.validate()
    times = np.asarray(times, dtype=float)
    brake = np.asarray(brake_pct, dtype=float)
    require(times.ndim == brake.ndim == 1 and len(times) == len(brake)
            and np.isfinite(times).all() and (np.diff(times) > 0).all(),
            'invalid_brake_samples', 'Brake timestamps must be finite, increasing and match sample count.')
    require(isinstance(max_gap_s, (int, float)) and math.isfinite(max_gap_s) and max_gap_s > 0,
            'invalid_brake_samples', 'Brake sample gap limit must be finite and positive.')
    finite_brake = brake[np.isfinite(brake)]
    require(((finite_brake >= 0) & (finite_brake <= 100)).all(), 'invalid_brake_samples',
            'Verified percentage brake samples must be between 0 and 100.')
    intervals = []
    start = None
    peak = 0.0
    count = 0
    observed = False

    def close(index, released):
        nonlocal start, peak, count, observed
        if start is None:
            return
        duration = float(times[index] - times[start])
        if duration >= settings.min_duration_s and peak >= settings.min_peak_pct:
            require(len(intervals) < 128, 'zone_limit', 'Recording has too many braking zones for one lap.')
            intervals.append({'start_time_s': float(times[start]),
                              'end_time_s': float(times[index]),
                              'peak_brake_pct': float(peak),
                              'sample_count': count,
                              'onset_observed': observed,
                              'release_observed': released})
        start = None
        peak = 0.0
        count = 0
        observed = False

    for index, value in enumerate(brake):
        gap = index > 0 and times[index] - times[index - 1] > max_gap_s
        if gap and start is not None:
            close(index - 1, False)
        if not math.isfinite(value):
            if start is not None:
                close(index - 1 if index > 0 else index, False)
            continue
        if start is None:
            if value >= settings.onset_pct:
                start = index
                peak = float(value)
                count = 1
                observed = bool(index > 0 and not gap and math.isfinite(brake[index - 1])
                                and brake[index - 1] < settings.onset_pct)
        elif value < settings.release_pct:
            close(index, True)
        else:
            peak = max(peak, float(value))
            count += 1
    if start is not None:
        close(len(times) - 1, False)
    return intervals


def match_positions(zones_a, zones_b, max_distance_m=100.0):
    """Maximum-cardinality, minimum-distance ordered one-to-one zone matches."""
    require(type(max_distance_m) in (int, float) and math.isfinite(max_distance_m)
            and 10 <= max_distance_m <= 300, 'invalid_match_range',
            'Use max_match_distance_m from 10 to 300 metres.')
    require(len(zones_a) <= 128 and len(zones_b) <= 128, 'zone_limit',
            'Too many braking zones to compare safely.')
    a = [float(z['start_distance_m']) for z in zones_a]
    b = [float(z['start_distance_m']) for z in zones_b]
    require(all(math.isfinite(v) for v in a + b) and a == sorted(a) and b == sorted(b),
            'invalid_zones', 'Braking zones must have finite start distances in track order.')
    n, m = len(a), len(b)
    count = [[0] * (m + 1) for _ in range(n + 1)]
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    choice = [[''] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            options = [(count[i + 1][j], -cost[i + 1][j], 'skip_a'),
                       (count[i][j + 1], -cost[i][j + 1], 'skip_b')]
            distance = abs(a[i] - b[j])
            if distance <= max_distance_m:
                options.append((1 + count[i + 1][j + 1],
                                -(distance + cost[i + 1][j + 1]), 'match'))
            best = max(options)
            count[i][j], cost[i][j], choice[i][j] = best[0], -best[1], best[2]
    pairs = []
    i = j = 0
    while i < n and j < m:
        action = choice[i][j]
        if action == 'match':
            pairs.append((i, j))
            i += 1
            j += 1
        elif action == 'skip_a':
            i += 1
        else:
            j += 1
    used_a = {i for i, _ in pairs}
    used_b = {j for _, j in pairs}
    return pairs, [i for i in range(n) if i not in used_a], [j for j in range(m) if j not in used_b]


def _clock_gap_between(session, start, end):
    clock = session.clock
    gaps = np.diff(clock) > session.clock_gap_limit
    return bool(np.any(gaps & (clock[:-1] < end) & (clock[1:] > start)))


def _distance_at(session, path, timestamp):
    times, distances, gap_limit = path
    index = int(np.searchsorted(times, timestamp, side='left'))
    if index < len(times) and abs(times[index] - timestamp) <= 1e-8:
        return float(distances[index])
    if index == 0 or index == len(times):
        return None
    left = index - 1
    if times[index] - times[left] > gap_limit or _clock_gap_between(session, timestamp, timestamp):
        return None
    fraction = (timestamp - times[left]) / (times[index] - times[left])
    return float(distances[left] + fraction * (distances[index] - distances[left]))


def _abs_usage(session, signal, start, end):
    if signal is None:
        return None, 0.0
    inside = (signal.times > start) & (signal.times < end)
    points = np.r_[start, signal.times[inside], end]
    values = session.sample('abs', points[:-1])
    durations = np.diff(points)
    covered = np.isfinite(values) & (durations <= signal.max_gap_s)
    return float(durations[covered & (values > 0)].sum()), float(durations[covered].sum())


def _throttle_pickup(session, signal, path, end_time, end_distance, next_start):
    if signal is None:
        return None
    deadline = min(float(session.clock[-1]), end_time + 5.0, next_start)
    if deadline < end_time:
        return None
    candidate_times = np.r_[end_time, signal.times[(signal.times > end_time) & (signal.times <= deadline)]]
    for timestamp in candidate_times:
        if _clock_gap_between(session, end_time, float(timestamp)):
            break
        value = session.sample('throttle', [timestamp])[0]
        if not np.isfinite(value):
            break
        distance = _distance_at(session, path, float(timestamp))
        if distance is None or distance > end_distance + 250:
            break
        if value >= 5:
            return {'distance_m': distance, 'delay_s': float(timestamp - end_time)}
    return None


def build_braking_zones(session, lap, path, settings: BrakingSettings):
    """Enrich native brake events only when speed and distance coverage support them."""
    settings.validate()
    brake = session.series('brake')
    require(brake.unit == '%', 'unknown_brake_unit',
            'Braking-zone analysis requires verified percentage brake units.')
    speed = session.series('speed')
    from .summary import speed_factor
    factor = speed_factor(speed.unit)
    require(factor is not None, 'unknown_speed_unit',
            'Braking-zone analysis requires verified km/h or m/s speed units.')
    mask = (brake.times >= lap['start_s']) & (brake.times < lap['end_s'])
    intervals = detect_intervals(brake.times[mask], brake.values[mask], brake.max_gap_s, settings)
    try:
        abs_signal = session.series('abs') if 'abs' in session.sources else None
    except InspectionError:
        abs_signal = None
    try:
        throttle_signal = session.series('throttle') if 'throttle' in session.sources else None
    except InspectionError:
        throttle_signal = None
    if throttle_signal is not None and throttle_signal.unit != '%':
        throttle_signal = None
    warnings = []
    if abs_signal is None:
        warnings.append('ABS signal unavailable; active time is null.')
    if throttle_signal is None:
        warnings.append('Verified percentage throttle unavailable; pickup is null.')
    skipped = {'distance_or_clock_gap': 0, 'speed_coverage': 0, 'insufficient_speed_drop': 0}
    zones = []
    for i, interval in enumerate(intervals):
        start = interval['start_time_s']
        end = interval['end_time_s']
        if _clock_gap_between(session, start, end):
            skipped['distance_or_clock_gap'] += 1
            continue
        start_distance = _distance_at(session, path, start)
        end_distance = _distance_at(session, path, end)
        if start_distance is None or end_distance is None or end_distance < start_distance:
            skipped['distance_or_clock_gap'] += 1
            continue
        speed_times = np.r_[start, speed.times[(speed.times > start) & (speed.times < end)], end]
        if np.any(np.diff(speed_times) > speed.max_gap_s):
            skipped['speed_coverage'] += 1
            continue
        speeds = session.sample('speed', speed_times) * factor
        if not np.isfinite(speeds).all():
            skipped['speed_coverage'] += 1
            continue
        initial_speed = float(speeds[0])
        minimum_speed = float(np.min(speeds))
        if initial_speed - minimum_speed < settings.min_speed_drop_kph:
            skipped['insufficient_speed_drop'] += 1
            continue
        abs_active, abs_coverage = _abs_usage(session, abs_signal, start, end)
        next_start = intervals[i + 1]['start_time_s'] if i + 1 < len(intervals) else lap['end_s']
        pickup = (_throttle_pickup(session, throttle_signal, path, end, end_distance, next_start)
                  if interval['release_observed'] else None)
        flags = []
        if not interval['onset_observed']:
            flags.append('onset_unobserved')
        if not interval['release_observed']:
            flags.append('release_unobserved')
        zones.append({
            'zone': len(zones) + 1,
            'start_distance_m': start_distance,
            'end_distance_m': end_distance,
            'braking_distance_m': end_distance - start_distance,
            'initial_speed_kph': initial_speed,
            'minimum_speed_kph': minimum_speed,
            'speed_drop_kph': initial_speed - minimum_speed,
            'peak_brake_pct': interval['peak_brake_pct'],
            'duration_s': end - start,
            'abs_active_time_s': abs_active,
            'abs_coverage_s': abs_coverage,
            'throttle_pickup_distance_m': pickup['distance_m'] if pickup else None,
            'throttle_pickup_delay_s': pickup['delay_s'] if pickup else None,
            'start_time_s': start,
            'end_time_s': end,
            'onset_observed': interval['onset_observed'],
            'release_observed': interval['release_observed'],
            'quality_flags': flags,
        })
    if any(skipped.values()):
        warnings.append('Some brake intervals were excluded for unsupported distance, timing or speed coverage, or insufficient speed drop.')
    return {'zones': zones, 'detected_brake_intervals': len(intervals),
            'excluded_intervals': skipped, 'warnings': warnings}
