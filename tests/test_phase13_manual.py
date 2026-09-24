"""Manual corner definitions are exact-match, bounded and path-confined."""
import json
import pytest
from lmu_mcp.database import InspectionError
from lmu_mcp.manual_corners import load_manual_corners


def write(directory,name,data):
    path=directory/name
    path.write_text(json.dumps(data),encoding='utf-8')
    return path


def definition(track='Synthetic',layout='Test',corners=None):
    return {'track':track,'layout':layout,'corners':corners or [
        {'corner_id':7,'name':'User Turn','start_distance_m':20,'end_distance_m':50},
        {'corner_id':8,'start_distance_m':60,'apex_distance_m':70,'end_distance_m':90}]}


def test_exact_track_layout_match_and_ordered_ranges(tmp_path):
    write(tmp_path,'track.json',definition(corners=[
        {'corner_id':8,'start_distance_m':60,'end_distance_m':90},
        {'corner_id':7,'name':'User Turn','start_distance_m':20,'end_distance_m':50}]))
    rows=load_manual_corners('Synthetic','Test',tmp_path)
    assert [r['corner_id'] for r in rows]==[7,8]
    assert all(r['source']=='manual' for r in rows)
    assert rows[0]['name']=='User Turn'
    assert load_manual_corners('synthetic','Test',tmp_path) is None
    assert load_manual_corners('Synthetic','Other',tmp_path) is None
    assert load_manual_corners(None,'Test',tmp_path) is None


def test_overlap_apex_and_duplicate_ids_rejected(tmp_path):
    path=write(tmp_path,'track.json',definition(corners=[
        {'corner_id':7,'start_distance_m':20,'end_distance_m':50},
        {'corner_id':8,'start_distance_m':45,'end_distance_m':90}]))
    with pytest.raises(InspectionError,match='must not overlap'):
        load_manual_corners('Synthetic','Test',tmp_path)
    path.write_text(json.dumps(definition(corners=[
        {'corner_id':7,'start_distance_m':20,'apex_distance_m':60,'end_distance_m':50}])),encoding='utf-8')
    with pytest.raises(InspectionError,match='apex distance'):
        load_manual_corners('Synthetic','Test',tmp_path)
    path.write_text(json.dumps(definition(corners=[
        {'corner_id':7,'start_distance_m':20,'end_distance_m':50},
        {'corner_id':7,'start_distance_m':60,'end_distance_m':90}])),encoding='utf-8')
    with pytest.raises(InspectionError,match='IDs must be unique'):
        load_manual_corners('Synthetic','Test',tmp_path)


def test_duplicate_matching_files_and_malformed_json_rejected(tmp_path):
    write(tmp_path,'one.json',definition())
    write(tmp_path,'two.json',definition())
    with pytest.raises(InspectionError,match='Multiple manual files'):
        load_manual_corners('Synthetic','Test',tmp_path)
    (tmp_path/'two.json').write_text('{',encoding='utf-8')
    with pytest.raises(InspectionError,match='valid UTF-8 JSON'):
        load_manual_corners('Synthetic','Test',tmp_path)


def test_file_count_and_size_bounded(tmp_path):
    for index in range(33):
        write(tmp_path,f'{index}.json',definition(track=f'Other {index}'))
    with pytest.raises(InspectionError,match='at most 32'):
        load_manual_corners('Synthetic','Test',tmp_path)
    for path in tmp_path.glob('*.json'):
        path.unlink()
    (tmp_path/'large.json').write_bytes(b' ' * 65537)
    with pytest.raises(InspectionError,match='at most 64 KiB'):
        load_manual_corners('Synthetic','Test',tmp_path)
