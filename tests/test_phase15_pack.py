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
