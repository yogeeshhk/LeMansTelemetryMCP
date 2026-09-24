"""Conservative sustained path-deviation detection independent of MCP transport."""
from dataclasses import dataclass
import math

import numpy as np

from ..telemetry import require


@dataclass(frozen=True)
class ExcursionSettings:
    min_duration_s: float = 0.3
    min_excess_m: float = 0.05
    max_events: int = 128

    def validate(self):
        require(
            isinstance(self.min_duration_s, (int, float))
            and not isinstance(self.min_duration_s, bool)
            and math.isfinite(self.min_duration_s)
            and 0.2 <= self.min_duration_s <= 5.0,
            "invalid_excursion_threshold",
            "Use min_duration_s from 0.2 to 5 seconds.",
        )
        require(
            isinstance(self.min_excess_m, (int, float))
            and not isinstance(self.min_excess_m, bool)
            and math.isfinite(self.min_excess_m)
            and 0 <= self.min_excess_m <= 2.0,
            "invalid_excursion_threshold",
            "Use min_excess_m from 0 to 2 metres.",
        )
        require(
            type(self.max_events) is int and 1 <= self.max_events <= 128,
            "invalid_excursion_threshold",
            "Use max_events from 1 to 128.",
        )
        return self


def detect_path_deviations(
    times,
    distances,
    path_lateral,
    track_edge,
    max_gap_s,
    settings=ExcursionSettings(),
):
    """Detect sustained vehicle-centre crossings of the approximate same-side edge.

    Missing samples, source/clock gaps and side changes split runs. The result is an
    unconfirmed path deviation; it is never an official track-limit decision.
    """
    settings.validate()
    arrays = [np.asarray(values, dtype=float) for values in
              (times, distances, path_lateral, track_edge)]
    times, distances, lateral, edge = arrays
    require(
        all(array.ndim == 1 and len(array) == len(times) for array in arrays)
        and len(times) >= 2
        and np.isfinite(times).all()
        and (np.diff(times) > 0).all(),
        "invalid_excursion_samples",
        "Excursion samples need matching one-dimensional arrays and finite increasing times.",
    )
    require(
        isinstance(max_gap_s, (int, float))
        and not isinstance(max_gap_s, bool)
        and math.isfinite(max_gap_s)
        and max_gap_s > 0,
        "invalid_excursion_samples",
        "Excursion sample gap limit must be finite and positive.",
    )
    finite_distance = distances[np.isfinite(distances)]
    require(
        len(finite_distance) >= 2 and (np.diff(finite_distance) >= 0).all(),
        "invalid_excursion_samples",
        "Excursion lap distances must be finite where used and must not reverse.",
    )
    signal_finite = np.isfinite(lateral) & np.isfinite(edge)
    require(
        signal_finite.any(),
        "unsupported_excursion_signals",
        "Path Lateral and Track Edge have no overlapping finite observations.",
    )
    nonzero = signal_finite & (np.abs(lateral) > 1e-6) & (np.abs(edge) > 1e-6)
    require(
        not np.any(nonzero & (np.sign(lateral) != np.sign(edge))),
        "ambiguous_edge_sign",
        "Track Edge is not consistently on the same signed side as Path Lateral.",
    )
    valid = signal_finite & np.isfinite(distances) & (np.abs(edge) > 1e-6)
    observed_duration = float(times[-1] - times[0])
    covered_duration = float(np.diff(times)[
        valid[:-1] & valid[1:] & (np.diff(times) <= max_gap_s)
    ].sum())
    outside = valid & ((np.abs(lateral) - np.abs(edge)) >= settings.min_excess_m)
    side = np.where(lateral < 0, "left", "right")
    events = []
    short_runs = 0
    start = None

    def close(end):
        nonlocal start, short_runs
        if start is None:
            return
        duration = float(times[end] - times[start])
        if duration + 1e-9 >= settings.min_duration_s:
            require(
                len(events) < settings.max_events,
                "excursion_limit",
                "Lap has too many sustained path deviations for one bounded request.",
            )
            indices = np.arange(start, end + 1)
            excess = np.abs(lateral[indices]) - np.abs(edge[indices])
            peak_index = int(indices[int(np.argmax(excess))])
            events.append({
                "side": str(side[start]),
                "start_time_s": float(times[start]),
                "end_time_s": float(times[end]),
                "duration_s": duration,
                "start_distance_m": float(distances[start]),
                "end_distance_m": float(distances[end]),
                "peak_distance_m": float(distances[peak_index]),
                "peak_excess_m": float(excess.max()),
                "sample_count": int(end - start + 1),
                "confidence": "unconfirmed",
            })
        else:
            short_runs += 1
        start = None

    for index in range(len(times)):
        split = (
            index > 0
            and (times[index] - times[index - 1] > max_gap_s
                 or not valid[index - 1]
                 or (start is not None and side[index] != side[start]))
        )
        if split:
            close(index - 1)
        if outside[index]:
            if start is None:
                start = index
        elif start is not None:
            close(index - 1)
    if start is not None:
        close(len(times) - 1)
    return {
        "status": "supported",
        "events": events,
        "short_runs_excluded": short_runs,
        "coverage_s": covered_duration,
        "observed_duration_s": observed_duration,
        "coverage_fraction": covered_duration / observed_duration if observed_duration > 0 else 0.0,
        "method": (
            "Sustained vehicle-centre Path Lateral magnitude beyond the same-side Track Edge "
            "magnitude. Missing samples, source/clock gaps and side changes split runs. The "
            "simulator describes the centre path as very approximate, so events are unconfirmed "
            "path deviations, not official track-limit violations."
        ),
    }
