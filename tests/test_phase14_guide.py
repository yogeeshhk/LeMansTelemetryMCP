import json
import duckdb
import pytest
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
from lmu_mcp.track_knowledge import validate_pack


def knowledge(name='Turn One', status='calibrated'):
    return validate_pack({'version': 1, 'track': 'Synthetic', 'layout': 'Test',
        'status': status, 'sources': [{'id': 'map', 'title': 'Circuit map',
        'url': 'https://example.org/map', 'retrieved': '2026-09-24'}],
        'features': [{'feature_id': 'turn-one', 'name': name, 'kind': 'corner',
        'order': 1, 'status': status, 'start_distance_m': 25,
        'end_distance_m': 70, 'uncertainty_m': 5,
        'distance_method': 'Reviewed synthetic laps', 'source_ids': ['map']}]})


def api(recording):
    return TelemetryService(Repository(recording.parent))


def test_guide_exact_match_paging_and_no_pack(recording, monkeypatch):
    service = api(recording)
    assert service.get_track_guide(recording.name)['pack_status'] == 'no_pack'
    pack = knowledge()
    pack['features'].append({'feature_id': 'straight', 'name': 'Straight',
        'kind': 'straight', 'order': 2, 'status': 'unmatched',
        'start_distance_m': None, 'end_distance_m': None,
        'uncertainty_m': None, 'distance_method': None,
        'source_ids': ['map'], 'character': None})
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge',
                        lambda track, layout: pack if (track, layout) == ('Synthetic', 'Test') else None)
    first = service.get_track_guide(recording.name, limit=1)
    assert first['pack_status'] == 'calibrated'
    assert first['features'][0]['feature_id'] == 'turn-one'
    assert first['next_offset'] == 1
    assert service.get_track_guide(recording.name, offset=1)['features'][0]['name'] == 'Straight'
    with pytest.raises(InspectionError, match='limit'):
        service.get_track_guide(recording.name, limit=51)


def test_unique_name_provenance_and_pack_edit_invalidate(corner_recording, monkeypatch):
    current = [knowledge()]
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge',
                        lambda track, layout: current[0])
    service = api(corner_recording)
    first = service.get_corners(corner_recording.name, 1)['corners'][0]
    assert first['name'] == 'Turn One'
    assert first['track_feature']['status'] == 'calibrated'
    assert first['track_feature']['sources'][0]['url'] == 'https://example.org/map'
    comparison = service.compare_corner(corner_recording.name, 1, [1, 2])
    assert comparison['reference_corner']['name'] == 'Turn One'
    assert comparison['comparisons'][0]['corner']['name'] == 'Turn One'
    current[0] = knowledge('Renamed Turn', 'approximate')
    updated = service.get_corners(corner_recording.name, 1)['corners'][0]
    assert updated['name'] == 'Renamed Turn'
    assert updated['track_feature']['status'] == 'approximate'


def test_manual_override_keeps_user_name(corner_recording, monkeypatch):
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge',
                        lambda track, layout: knowledge())
    manual = [{'corner_id': 7, 'name': 'My Name', 'source': 'manual',
               'start_distance_m': 20., 'end_distance_m': 70.,
               'apex_distance_m': 45.}]
    monkeypatch.setattr('lmu_mcp.service.load_manual_corners',
                        lambda track, layout: manual)
    corner = api(corner_recording).get_corners(corner_recording.name, 1)['corners'][0]
    assert corner['name'] == 'My Name'
    assert 'track_feature' not in corner


def test_unmatched_automatic_corner_stays_unnamed(corner_recording, monkeypatch):
    pack = knowledge()
    pack['features'][0]['start_distance_m'] = 75
    pack['features'][0]['end_distance_m'] = 90
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge',
                        lambda track, layout: pack)
    corner = api(corner_recording).get_corners(corner_recording.name, 1)['corners'][0]
    assert corner['name'] is None
    assert 'track_feature' not in corner
