"""Time-domain braking intervals and ordered distance matching."""
from dataclasses import dataclass
import math
import numpy as np

from ..telemetry import require


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
