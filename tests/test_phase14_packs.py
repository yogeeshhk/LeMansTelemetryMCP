"""Synthetic sourced track packs never depend on real telemetry."""
import json
import pytest
from lmu_mcp.database import InspectionError
from lmu_mcp.track_knowledge import load_track_knowledge, validate_pack


def pack(features=None):
    return {'version': 1, 'track': 'Synthetic', 'layout': 'Test', 'status': 'calibrated',
            'sources': [{'id': 'map', 'title': 'Circuit map',
                         'url': 'https://example.org/map', 'retrieved': '2026-09-24'}],
            'features': features or [
                {'feature_id': 'one', 'name': 'Turn One', 'kind': 'corner', 'order': 1,
                 'status': 'calibrated', 'start_distance_m': 20, 'end_distance_m': 50,
                 'uncertainty_m': 5, 'distance_method': 'Reviewed two synthetic laps',
                 'source_ids': ['map']}]}


def write(directory, name, data):
    path = directory / name
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_exact_match_and_noncorner_overlap(tmp_path):
    data = pack()
    data['features'].append({'feature_id': 'sector', 'name': 'Sector 1', 'kind': 'sector',
                             'order': 2, 'status': 'calibrated', 'start_distance_m': 0,
                             'end_distance_m': 100, 'uncertainty_m': 0,
                             'distance_method': 'Source line', 'source_ids': ['map']})
    write(tmp_path, 'test.json', data)
    result = load_track_knowledge('Synthetic', 'Test', tmp_path)
    assert result['features'][0]['name'] == 'Turn One'
    assert result['features'][1]['kind'] == 'sector'
    assert result['sources'][0]['url'] == 'https://example.org/map'
    assert load_track_knowledge('synthetic', 'Test', tmp_path) is None
    assert load_track_knowledge('Synthetic', 'Other', tmp_path) is None


def test_bad_ranges_sources_ids_and_types_rejected():
    data = pack()
    data['features'].append({**data['features'][0], 'feature_id': 'two', 'order': 2,
                             'start_distance_m': 40, 'end_distance_m': 70})
    with pytest.raises(InspectionError, match='must not overlap'):
        validate_pack(data)
    data = pack()
    data['features'][0]['source_ids'] = ['missing']
    with pytest.raises(InspectionError, match='source_ids'):
        validate_pack(data)
    data['features'][0]['source_ids'] = [{}]
    with pytest.raises(InspectionError, match='source_ids'):
        validate_pack(data)
    data = pack()
    data['sources'][0]['url'] = 'http://example.org/map'
    with pytest.raises(InspectionError, match='HTTPS'):
        validate_pack(data)
    data = pack()
    data['features'][0]['status'] = 'unmatched'
    with pytest.raises(InspectionError, match='Unmatched'):
        validate_pack(data)


def test_duplicate_invalid_json_and_bounds(tmp_path):
    write(tmp_path, 'one.json', pack())
    write(tmp_path, 'two.json', pack())
    with pytest.raises(InspectionError, match='Multiple track packs'):
        load_track_knowledge('Synthetic', 'Test', tmp_path)
    (tmp_path / 'two.json').write_text('{', encoding='utf-8')
    with pytest.raises(InspectionError, match='UTF-8 JSON'):
        load_track_knowledge('Synthetic', 'Test', tmp_path)
    (tmp_path / 'two.json').unlink()
    (tmp_path / 'one.json').write_bytes(b' ' * 65537)
    with pytest.raises(InspectionError, match='64 KiB'):
        load_track_knowledge('Synthetic', 'Test', tmp_path)
    (tmp_path / 'one.json').unlink()
    for index in range(33):
        write(tmp_path, f'{index}.json', pack())
    with pytest.raises(InspectionError, match='at most 32'):
        load_track_knowledge('Synthetic', 'Test', tmp_path)


def test_symlink_cannot_escape_pack_directory(tmp_path):
    inside = tmp_path / 'inside'
    inside.mkdir()
    outside = write(tmp_path, 'outside.json', pack())
    try:
        (inside / 'escape.json').symlink_to(outside)
    except OSError:
        pytest.skip('File symlinks unavailable on this Windows account')
    with pytest.raises(InspectionError, match='inside its fixed directory'):
        load_track_knowledge('Synthetic', 'Test', inside)
