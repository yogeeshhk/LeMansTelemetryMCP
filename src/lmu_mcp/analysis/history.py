"""Bounded recorded-time selection and evidence-based corner experiments."""
import math


LMP3_SETUP_SOURCE = {
    "id": "lmu-lmp3-setup-2025",
    "title": "Le Mans Ultimate LMP3 Quick Setup Guide",
    "url": "https://lemansultimate.com/lmp3-quick-setup-guide/",
    "published": "2025-12-22",
    "applicable_models": ["Ligier JS P325", "Ginetta G61 LT P325 EVO"],
}
TC_SOURCE = {
    "id": "lmu-traction-control",
    "title": "How do I configure my traction control in Le Mans Ultimate?",
    "url": "https://guide.lemansultimate.com/hc/en-gb/articles/13182869047311-How-do-I-configure-my-traction-control-in-Le-Mans-Ultimate",
    "applicability": "LMU cars exposing the named TC controls; recorded integer direction remains unverified.",
}

PHASE_FIELDS = {
    "entry": ("entry_speed_kph", "brake_point_m", "turn_in_position_m"),
    "mid": ("minimum_speed_kph", "minimum_speed_position_m",
            "maximum_absolute_steering_pct"),
    "exit": ("throttle_pickup_position_m", "full_throttle_position_m",
             "exit_speed_kph", "tc_active_time_s"),
}


def select_ranked_laps(candidates, limit=3):
    """Use positive recorded lap times only; fastest and slowest groups are disjoint."""
    timed = [row for row in candidates
             if type(row.get("lap_time_s")) in (int, float)
             and math.isfinite(row["lap_time_s"]) and row["lap_time_s"] > 0]
    fastest_pool = [row for row in timed if row.get("benchmark_candidate") is True and row.get("distance_valid") is True]
    fastest = sorted(fastest_pool,
                     key=lambda row: (row["lap_time_s"], row["session_id"], row["lap"]))[:limit]
    used = {(row["session_id"], row["lap"]) for row in fastest}
    slowest_pool = [row for row in timed if row.get("complete") is True
                    and row.get("distance_valid") is True
                    and (row["session_id"], row["lap"]) not in used]
    slowest = sorted(slowest_pool,
                     key=lambda row: (-row["lap_time_s"], row["session_id"], row["lap"]))[:limit]
    selected = []
    for role, rows in (("fastest", fastest), ("slowest", slowest)):
        for row in rows:
            selected.append({**row, "selection": role,
                             "timing_source": "recorded Lap Time event"})
    return {
        "status": "ranked" if selected else "unsupported_timing",
        "selected": selected,
        "timed_sample_count": len(timed),
        "fastest_candidate_count": len(fastest_pool),
        "complete_distance_valid_count": sum(
            row.get("complete") is True and row.get("distance_valid") is True
            for row in candidates
        ),
        "method": "Up to three fastest benchmark candidates and three disjoint slowest complete distance-valid laps by positive recorded Lap Time; no boundary-duration ranking.",
    }


def summarize_corner_evidence(rows):
    """Summarize measured corner metrics without filling missing values."""
    result = []
    for phase, fields in PHASE_FIELDS.items():
        for field in fields:
            groups = {}
            for role in ("fastest", "slowest"):
                values = [row["metrics"].get(field) for row in rows
                          if row.get("selection") == role and not row.get("quality_flags")
                          and type(row["metrics"].get(field)) in (int, float)
                          and math.isfinite(row["metrics"][field])]
                groups[role] = values
            fast, slow = groups["fastest"], groups["slowest"]
            result.append({
                "phase": phase,
                "metric": field,
                "fastest_mean": sum(fast) / len(fast) if fast else None,
                "slowest_mean": sum(slow) / len(slow) if slow else None,
                "slowest_minus_fastest": (
                    sum(slow) / len(slow) - sum(fast) / len(fast)
                    if fast and slow else None
                ),
                "fastest_samples": len(fast),
                "slowest_samples": len(slow),
                "repeated": len(fast) >= 2 and len(slow) >= 2,
            })
    return result


def _evidence(evidence, metric):
    return next((row for row in evidence if row["metric"] == metric), None)


def _source_model(car_name):
    if not isinstance(car_name, str):
        return None
    folded = car_name.casefold()
    return next((model for model in LMP3_SETUP_SOURCE["applicable_models"]
                 if model.casefold() in folded), None)


def build_experiments(evidence, car_name, settings):
    """Return source-applicable one-setting tests or a driving/feedback fallback."""
    available = {row["setting_id"]: row for row in settings}
    model = _source_model(car_name)
    experiments = []
    turn_in = _evidence(evidence, "turn_in_position_m")
    minimum_speed = _evidence(evidence, "minimum_speed_kph")
    steering = _evidence(evidence, "maximum_absolute_steering_pct")
    if model and "VM_DIFF_PRELOAD" in available and turn_in and turn_in["repeated"]:
        late = turn_in["slowest_minus_fastest"]
        speed = minimum_speed["slowest_minus_fastest"] if minimum_speed else None
        if late is not None and late >= 2 and speed is not None and speed <= -1:
            experiments.append({
                "rank": len(experiments) + 1,
                "setting_id": "VM_DIFF_PRELOAD",
                "conditional_symptom": "Slower selected laps repeatedly turn in later and carry at least 1 km/h less minimum speed.",
                "proposed_direction": "Decrease differential preload by one producer-displayed step.",
                "expected_tradeoff": "The cited car guide associates lower preload with more entry rotation; verify that added rotation does not reduce braking/entry stability.",
                "source_id": LMP3_SETUP_SOURCE["id"],
                "source_applicability": model,
                "next_run_measurement": "Hold fuel, tyres and weather comparable; compare turn-in position, minimum speed, section time and path-deviation overlap over at least three laps per setting.",
            })
    if model and "VM_FRONT_ANTISWAY" in available and steering and steering["repeated"]:
        delta = steering["slowest_minus_fastest"]
        if delta is not None and delta >= 3:
            experiments.append({
                "rank": len(experiments) + 1,
                "setting_id": "VM_FRONT_ANTISWAY",
                "conditional_symptom": "Slower selected laps repeatedly require at least 3 percentage points more absolute steering through the corner.",
                "proposed_direction": "Soften the front anti-roll bar by one producer-displayed step.",
                "expected_tradeoff": "The cited car guide says a softer front bar can improve response but may reduce stability.",
                "source_id": LMP3_SETUP_SOURCE["id"],
                "source_applicability": model,
                "next_run_measurement": "Compare maximum steering, minimum speed, entry stability, section time and deviations over at least three laps per setting.",
            })
    experiments = experiments[:3]
    exit_pickup = _evidence(evidence, "throttle_pickup_position_m")
    feedback = []
    if exit_pickup and exit_pickup["repeated"] and exit_pickup["slowest_minus_fastest"] is not None \
            and exit_pickup["slowest_minus_fastest"] >= 3:
        feedback.append(
            "Throttle pickup is repeatedly later in the slower group. Report whether this follows wheelspin, understeer, oversteer or traffic before changing a TC index; the source defines TC functions but not recorded index direction."
        )
    if experiments:
        next_step = "Run one experiment at a time; do not combine setting changes."
    else:
        next_step = (
            "Keep the setup fixed and repeat at least three comparable laps while testing a calmer entry and progressive throttle. Record whether the limitation feels like entry rotation, mid-corner balance, exit traction or traffic before requesting a setup direction."
        )
    return {"experiments": experiments, "feedback_requests": feedback,
            "next_step": next_step, "applicable_setup_model": model,
            "sources": [{**LMP3_SETUP_SOURCE, "applicable": model is not None},
                        {**TC_SOURCE, "applicable": True}]}
