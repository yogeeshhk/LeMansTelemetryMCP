"""Recorded-time selection and conservative corner experiment synthesis."""
from lmu_mcp.analysis.history import (
    build_experiments, select_ranked_laps, summarize_corner_evidence,
)


def lap(session, number, time, candidate=True, complete=True, valid=True, flags=None):
    return {"session_id": session, "lap": number, "lap_time_s": time,
            "benchmark_candidate": candidate, "complete": complete,
            "distance_valid": valid, "flags": flags or []}


def metric_row(selection, turn_in, minimum_speed, steering, pickup=50):
    return {"selection": selection, "quality_flags": [], "metrics": {
        "entry_speed_kph": 100, "brake_point_m": 10,
        "turn_in_position_m": turn_in, "minimum_speed_kph": minimum_speed,
        "minimum_speed_position_m": 40,
        "maximum_absolute_steering_pct": steering,
        "throttle_pickup_position_m": pickup, "full_throttle_position_m": 70,
        "exit_speed_kph": 110, "tc_active_time_s": 0,
    }}


def settings(*ids):
    return [{"setting_id": setting_id} for setting_id in ids]


def test_ranking_uses_recorded_time_and_disjoint_good_bad_groups():
    candidates = [
        lap("a", 1, 90), lap("a", 2, 95, candidate=False, flags=["pit_lane"]),
        lap("b", 1, 91), lap("b", 2, 96, candidate=False),
        lap("c", 1, 92), lap("c", 2, 97, candidate=False),
        lap("d", 1, None), lap("d", 2, 200, complete=False),
    ]
    result = select_ranked_laps(candidates)
    assert [(row["session_id"], row["lap"]) for row in result["selected"]] == [
        ("a", 1), ("b", 1), ("c", 1), ("c", 2), ("b", 2), ("a", 2)
    ]
    assert [row["selection"] for row in result["selected"]] == ["fastest"] * 3 + ["slowest"] * 3
    assert all(row["timing_source"] == "recorded Lap Time event" for row in result["selected"])


def test_missing_recorded_timing_returns_no_ranking():
    result = select_ranked_laps([lap("a", 1, None), lap("a", 2, 0)])
    assert result["status"] == "unsupported_timing" and result["selected"] == []


def test_repeated_ligier_evidence_yields_two_single_setting_tests():
    rows = [metric_row("fastest", 20, 80, 10), metric_row("fastest", 21, 81, 11),
            metric_row("slowest", 25, 75, 16, 56), metric_row("slowest", 26, 76, 17, 57)]
    evidence = summarize_corner_evidence(rows)
    result = build_experiments(
        evidence, "Example Ligier JS P325", settings("VM_DIFF_PRELOAD", "VM_FRONT_ANTISWAY")
    )
    assert [row["setting_id"] for row in result["experiments"]] == [
        "VM_DIFF_PRELOAD", "VM_FRONT_ANTISWAY"
    ]
    assert all("one producer-displayed step" in row["proposed_direction"]
               for row in result["experiments"])
    assert result["applicable_setup_model"] == "Ligier JS P325"
    assert result["feedback_requests"]


def test_wrong_car_missing_setting_and_weak_history_produce_no_setup_advice():
    strong = summarize_corner_evidence([
        metric_row("fastest", 20, 80, 10), metric_row("fastest", 21, 81, 11),
        metric_row("slowest", 25, 75, 16), metric_row("slowest", 26, 76, 17),
    ])
    assert build_experiments(strong, "Some GT3", settings("VM_DIFF_PRELOAD"))["experiments"] == []
    assert build_experiments(strong, "Ligier JS P325", settings())["experiments"] == []
    weak = summarize_corner_evidence([
        metric_row("fastest", 20, 80, 10), metric_row("slowest", 20, 80, 10)
    ])
    result = build_experiments(weak, "Ligier JS P325", settings("VM_DIFF_PRELOAD"))
    assert result["experiments"] == []
    assert "Keep the setup fixed" in result["next_step"]
