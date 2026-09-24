"""La Sarthe source-pack contract; no private telemetry fixtures."""
from copy import deepcopy

from lmu_mcp.track_knowledge import load_track_knowledge, match_detected_corner, validate_pack


def test_la_sarthe_pack_exact_layout_and_full_lap_order():
    pack = load_track_knowledge('Circuit de la Sarthe', 'Circuit de la Sarthe')
    assert pack['status'] == 'calibrated'
    assert len(pack['features']) == 15
    assert [feature['order'] for feature in pack['features']] == list(range(1, 16))
    assert [feature['feature_id'] for feature in pack['features']] == [
        'pit-straight', 'dunlop-curve', 'dunlop-chicane', 'forest-esses',
        'tertre-rouge', 'mulsanne-straight', 'daytona-chicane',
        'michelin-chicane', 'mulsanne-corner', 'indianapolis', 'arnage',
        'porsche-curves', 'karting-esses', 'ford-chicanes', 'motul-turn']
    assert len(pack['sources']) == 3
    assert all(source['url'].startswith('https://') for source in pack['sources'])
    assert all(source['retrieved'] == '2026-09-25' for source in pack['sources'])
    assert load_track_knowledge('Circuit de la Sarthe', 'Other layout') is None
    assert load_track_knowledge('Other circuit', 'Circuit de la Sarthe') is None


def test_la_sarthe_measured_names_and_unsupported_complexes():
    pack = load_track_knowledge('Circuit de la Sarthe', 'Circuit de la Sarthe')
    expected = [(1540, 1640, 'tertre-rouge'), (7698, 7780, 'mulsanne-corner'),
                (9780, 9880, 'indianapolis'), (10120, 10200, 'arnage')]
    for start, end, feature_id in expected:
        match = match_detected_corner({'start_distance_m': start, 'end_distance_m': end}, pack)
        assert match['feature_id'] == feature_id
        assert match['status'] == 'calibrated'
    for start, end in [(800, 870), (4080, 4160), (6040, 6140), (12150, 12290),
                       (13300, 13370), (11000, 11100)]:
        assert match_detected_corner({'start_distance_m': start, 'end_distance_m': end}, pack) is None
    assert all(feature['start_distance_m'] is None for feature in pack['features']
               if feature['status'] == 'unmatched')


def test_la_sarthe_pack_is_valid_under_loader_schema():
    pack = load_track_knowledge('Circuit de la Sarthe', 'Circuit de la Sarthe')
    assert validate_pack(deepcopy(pack)) == pack


def test_shifted_boundary_and_missing_feature_do_not_invent_name():
    pack = load_track_knowledge('Circuit de la Sarthe', 'Circuit de la Sarthe')
    measured = {'start_distance_m': 9765, 'end_distance_m': 9900}
    assert match_detected_corner(measured, pack)['feature_id'] == 'indianapolis'
    shifted = {'start_distance_m': 9580, 'end_distance_m': 9700}
    assert match_detected_corner(shifted, pack) is None
    missing = deepcopy(pack)
    missing['features'] = [f for f in missing['features'] if f['feature_id'] != 'indianapolis']
    assert match_detected_corner(measured, missing) is None


def test_source_revision_changes_guide_and_cached_corner_provenance(corner_recording, monkeypatch, tmp_path):
    import json
    from lmu_mcp.database import Repository
    from lmu_mcp.service import TelemetryService
    from lmu_mcp import track_knowledge

    original = load_track_knowledge('Circuit de la Sarthe', 'Circuit de la Sarthe')
    raw = deepcopy(original)
    raw['track'], raw['layout'] = 'Synthetic', 'Test'
    raw['features'] = [deepcopy(next(f for f in original['features']
                                    if f['feature_id'] == 'tertre-rouge'))]
    raw['features'][0].update(order=1, start_distance_m=25, end_distance_m=70,
                              uncertainty_m=5, distance_method='Two synthetic laps')
    directory = tmp_path / 'packs'
    directory.mkdir()
    path = directory / 'test.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge',
                        lambda track, layout: track_knowledge.load_track_knowledge(track, layout, directory))
    service = TelemetryService(Repository(corner_recording.parent))
    first = service.get_corners(corner_recording.name, 1)['corners'][0]
    assert first['track_feature']['sources'][0]['retrieved'] == '2026-09-25'
    raw['sources'][0]['retrieved'] = '2026-09-26'
    path.write_text(json.dumps(raw), encoding='utf-8')
    updated = service.get_corners(corner_recording.name, 1)['corners'][0]
    assert updated['track_feature']['sources'][0]['retrieved'] == '2026-09-26'
    assert updated['minimum_speed_kph'] == first['minimum_speed_kph']
    assert service.get_track_guide(corner_recording.name)['sources'][0]['retrieved'] == '2026-09-26'
