"""Monza source-only pack and conservative future association behavior."""
from copy import deepcopy

from lmu_mcp.track_knowledge import (
    load_track_knowledge,
    match_detected_corners,
    validate_pack,
)


TRACK = "Autodromo Nazionale Monza"
LAYOUT = "Monza Curva Grande Circuit"


def turn(start, end):
    return {"start_distance_m": start, "end_distance_m": end}


def test_monza_pack_is_exact_approximate_and_complete():
    pack = load_track_knowledge(TRACK, LAYOUT)
    assert validate_pack(deepcopy(pack)) == pack
    assert pack["status"] == "approximate"
    assert [feature["feature_id"] for feature in pack["features"]] == [
        "start-finish-straight",
        "rettifilo",
        "biassono",
        "roggia",
        "lesmo-one",
        "lesmo-two",
        "serraglio",
        "ascari",
        "opposite-straight",
        "alboreto",
        "finish-approach",
    ]
    assert all(feature["status"] == "approximate" for feature in pack["features"])
    assert all(feature["start_distance_m"] is not None for feature in pack["features"])
    assert all(feature["uncertainty_m"] > 0 for feature in pack["features"])
    assert all(feature["coaching"][0]["evidence"] == "general_technique"
               for feature in pack["features"])
    assert {note["topic"] for note in pack["coaching"]} == {
        "overview", "setup", "race", "practice"
    }
    assert len(pack["sources"]) == 4
    assert all(source["retrieved"] == "2026-09-25" for source in pack["sources"])
    assert load_track_knowledge(TRACK, "Monza Junior Circuit") is None
    assert load_track_knowledge("Monza", LAYOUT) is None


def test_future_unique_matches_keep_approximate_status():
    pack = load_track_knowledge(TRACK, LAYOUT)
    matches = match_detected_corners(
        [turn(1050, 1450), turn(2290, 2480), turn(2670, 2870), turn(5080, 5480)],
        pack,
    )
    assert [match["feature_id"] for match in matches] == [
        "biassono", "lesmo-one", "lesmo-two", "alboreto"
    ]
    assert all(match["status"] == "approximate" for match in matches)
    assert all(match is None for match in match_detected_corners(
        [turn(680, 900), turn(1900, 2160), turn(3970, 4350)], pack
    ))


def test_future_calibration_replacement_requires_explicit_pack_revision():
    approximate = load_track_knowledge(TRACK, LAYOUT)
    measured = turn(2290, 2480)
    assert match_detected_corners([measured], approximate)[0]["status"] == "approximate"

    revised = deepcopy(approximate)
    revised["status"] = "calibrated"
    for feature in revised["features"]:
        if feature["feature_id"] == "lesmo-one":
            feature.update(
                status="calibrated",
                start_distance_m=2280,
                end_distance_m=2500,
                uncertainty_m=40,
                distance_method="Reviewed against two future synthetic valid laps.",
            )
    revised = validate_pack(revised)
    replacement = match_detected_corners([measured], revised)[0]
    assert replacement["feature_id"] == "lesmo-one"
    assert replacement["status"] == "calibrated"
    assert approximate["status"] == "approximate"


def test_car_specific_setup_notes_do_not_become_universal():
    pack = load_track_knowledge(TRACK, LAYOUT)
    note = next(item for item in pack["coaching"] if "Genesis GMR-001" in item["text"])
    assert note["evidence"] == "sourced"
    assert set(note["source_ids"]) == {"lmu-v12", "lmu-v131"}
    assert "Only the named car" in note["applicability"]
    assert "recorded BMW Hypercar" in note["applicability"]
