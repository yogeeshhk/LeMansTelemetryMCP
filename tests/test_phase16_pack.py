"""Spa pack and split/merged associations use deterministic synthetic ranges."""
from copy import deepcopy
from lmu_mcp.track_knowledge import load_track_knowledge, match_detected_corners, validate_pack

SPA = 'Circuit de Spa-Francorchamps'


def turn(start, end):
    return {'start_distance_m': start, 'end_distance_m': end}


def test_spa_exact_identity_order_and_coaching_coverage():
    pack = load_track_knowledge(SPA, SPA)
    assert validate_pack(deepcopy(pack)) == pack
    assert pack['status'] == 'calibrated'
    assert [f['feature_id'] for f in pack['features']] == [
        'pit-straight', 'la-source', 'eau-rouge-raidillon', 'kemmel', 'les-combes',
        'bruxelles', 'speaker-corner', 'pouhon', 'fagnes', 'campus', 'paul-frere',
        'blanchimont', 'bus-stop']
    assert {n['topic'] for n in pack['coaching']} == {'overview', 'setup', 'race', 'practice'}
    assert all(f['coaching'][0]['evidence'] == 'general_technique' for f in pack['features'])
    assert load_track_knowledge(SPA, 'Endurance') is None
    assert load_track_knowledge('Spa', SPA) is None
    assert all(s['retrieved'] == '2026-09-25' for s in pack['sources'])
    aero = next(n for n in pack['coaching'] if 'aero package' in n['text'])
    assert 'Oreca 07 LMP2+' in aero['applicability']
    assert 'GT3' in aero['text']


def test_split_detections_are_not_named_twice_and_complexes_stay_context():
    pack = load_track_knowledge(SPA, SPA)
    # Split La Source; single Campus. These are synthetic, not copied lap samples.
    matches = match_detected_corners([turn(210, 265), turn(275, 335), turn(4760, 4870)], pack)
    assert matches[:2] == [None, None]
    assert matches[2]['feature_id'] == 'campus'
    assert match_detected_corners([turn(210, 335)], pack)[0]['feature_id'] == 'la-source'
    # Merged or split portions of named multi-turn sequences never become one corner.
    for ranges in [[turn(950, 1100)], [turn(2260, 2440), turn(2450, 2600)],
                   [turn(3700, 4020)], [turn(4310, 4610)], [turn(6560, 6720)]]:
        assert all(m is None for m in match_detected_corners(ranges, pack))
    assert match_detected_corners([turn(2800, 3260)], pack) == [None]
    shifted = turn(4590, 4700)
    assert match_detected_corners([shifted], pack) == [None]
    missing = deepcopy(pack)
    missing['features'] = [f for f in pack['features'] if f['feature_id'] != 'campus']
    assert match_detected_corners([turn(4760, 4870)], missing) == [None]


def test_service_suppresses_split_names_without_changing_metrics(corner_recording, monkeypatch):
    from lmu_mcp.database import Repository
    from lmu_mcp.service import TelemetryService
    from tests.test_phase14_packs import pack as synthetic_pack
    service = TelemetryService(Repository(corner_recording.parent))
    baseline = service.get_corners(corner_recording.name, 1)['corners'][0]
    raw = synthetic_pack()
    raw['features'][0].update(start_distance_m=20, end_distance_m=80)
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge', lambda *args: validate_pack(raw))
    import lmu_mcp.service as module
    automatic = module.automatic_ranges
    def split(*args):
        rows, resolution = automatic(*args)
        row = rows[0]
        middle = (row['start_distance_m'] + row['end_distance_m']) / 2
        return [{**row, 'end_distance_m': middle},
                {**row, 'corner_id': 2, 'start_distance_m': middle}], resolution
    monkeypatch.setattr(module, 'automatic_ranges', split)
    rows = service.get_corners(corner_recording.name, 1)['corners']
    assert len(rows) == 2
    assert all('track_feature' not in row for row in rows)
    monkeypatch.setattr(module, 'automatic_ranges', automatic)
    service = TelemetryService(Repository(corner_recording.parent))
    named = service.get_corners(corner_recording.name, 1)['corners'][0]
    assert named['track_feature']['feature_id'] == 'one'
    assert named['minimum_speed_kph'] == baseline['minimum_speed_kph']
