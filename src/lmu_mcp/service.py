"""Direct Python coaching API; database connections live for one request only."""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import json
import math
import numpy as np
from . import config
from .database import Repository, InspectionError, inspect_connection
from .telemetry import Session, require
from .analysis.laps import identify_laps, select_lap
from .analysis.summary import lap_summary, speed_factor, control_transitions, match_onsets
from .alignment import distance_path, make_grid, aligned


def serializable(value):
    if isinstance(value,np.ndarray): return serializable(value.tolist())
    if isinstance(value,np.generic): return serializable(value.item())
    if isinstance(value,float): return round(value,4) if math.isfinite(value) else None
    if isinstance(value,dict): return {str(k):serializable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [serializable(v) for v in value]
    return value


def output(value):
    result=serializable(value)
    require(len(json.dumps(result,allow_nan=False).encode('utf-8'))<=config.MAX_OUTPUT_BYTES,
            'response_limit','Response is too large; request fewer channels/laps, a smaller range or coarser resolution.')
    return result


class TelemetryService:
    def __init__(self, repository=None):
        self.repository=repository or Repository()

    @contextmanager
    def session(self, session_id):
        require(isinstance(session_id,str) and 0<len(session_id)<=512,'invalid_session','Use a session ID from list_sessions.')
        with self.repository.open(session_id) as c:
            yield Session(c,inspect_connection(c,session_id))

    def list_sessions(self, search='', offset=0, limit=20):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'invalid_page','Use a nonnegative offset and limit from 1 to 100.')
        require(isinstance(search,str) and len(search)<=128,'invalid_search','Search must be at most 128 characters.')
        rows=[row for row in self.repository.discover() if search.casefold() in row['session_id'].casefold()]
        rows.sort(key=lambda r:(r.get('modified_ns',0),r['session_id']),reverse=True)
        selected=[]
        for row in rows[offset:offset+limit]:
            selected.append({'session_id':row['session_id'],'filename':Path(row['session_id']).name,
                             'modified_at':datetime.fromtimestamp(row['modified_ns']/1e9,timezone.utc).isoformat() if 'modified_ns' in row else None,
                             'size_bytes':row.get('size_bytes'),'status':row['status']})
        return output({'sessions':selected,'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None})

    def get_session_info(self, session_id):
        with self.session(session_id) as s:
            warnings=list(s.inspection.warnings)
            duration=None;laps=None
            try: duration=float(s.clock[-1]-s.clock[0]);laps=identify_laps(s)
            except InspectionError as e: warnings.append(e.code+': '+str(e))
            return output({'session_id':session_id,'car':s.metadata.get('CarName'),'car_class':s.metadata.get('CarClass'),
                           'track':s.metadata.get('TrackName'),'track_layout':s.metadata.get('TrackLayout'),
                           'session_type':s.metadata.get('SessionType'),'start_time':s.metadata.get('RecordingTime'),
                           'weather':s.metadata.get('WeatherConditions'),'session_duration_s':duration,
                           'number_of_laps':sum(r['complete'] for r in laps) if laps is not None else None,
                           'recorded_intervals':len(laps) if laps is not None else None,
                           'available_channels':list(s.sources),'sample_rates_hz':sorted({v['frequency_hz'] for v in s.inspection.catalog.values() if v['frequency_hz']}),
                           'database_tables':[{'schema':t.schema,'table':t.name,'kind':t.kind,'rows':t.row_count} for t in s.inspection.tables],
                           'warnings':warnings,'validity_note':'Official validity is unavailable; benchmark eligibility is a separate heuristic.'})

    def list_channels(self, session_id):
        with self.session(session_id) as s:
            rows=[]
            for name,source in s.sources.items():
                table=next(t for t in s.inspection.tables if (t.schema,t.name)==(source.schema,source.table))
                rows.append({'name':name,'source':source.table,'source_columns':list(source.value_columns),
                             'timestamp_column':source.timestamp_column,'unit':source.unit,'frequency_hz':source.frequency_hz,
                             'sample_count':table.row_count,'kind':source.kind,'extrema':s.reader.extrema(source)})
            return output({'channels':rows,'missing_canonical_channels':s.inspection.channels.missing,
                           'ambiguous_canonical_channels':list(s.inspection.channels.ambiguous),
                           'component_syntax':'Use name:value1 for multi-component channels; wheel order is unverified.',
                           'warnings':s.inspection.warnings})

    def list_laps(self, session_id, offset=0, limit=50):
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'invalid_page','Use offset >=0 and limit 1..100.')
        with self.session(session_id) as s:
            laps=identify_laps(s)
            speed=None;factor=None
            try: speed=s.series('speed');factor=speed_factor(speed.unit)
            except InspectionError: pass
            rows=[]
            for lap in laps[offset:offset+limit]:
                inside=(s.clock>=lap['start_s'])&(s.clock<lap['end_s'])
                values=speed.values[(speed.times>=lap['start_s'])&(speed.times<lap['end_s'])] if speed is not None else np.array([])
                values=values[np.isfinite(values)]
                rows.append({**lap,'sample_count':int(inside.sum()),'max_speed_kph':float(values.max()*factor) if len(values) and factor else None})
            return output({'laps':rows,'total':len(laps),'next_offset':offset+limit if offset+limit<len(laps) else None,
                           'lap_id_note':'lap is a unique interval ID in recording order; recorded_lap_number is the producer completion counter. Partial intervals are retained.'})

    def get_lap_summary(self, session_id, lap):
        with self.session(session_id) as s: return output(lap_summary(s,select_lap(s,lap)))

    def get_telemetry(self, session_id, lap, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=2.0):
        channels=['speed','brake','throttle','steering','gear'] if channels is None else channels
        with self.session(session_id) as s:
            info=select_lap(s,lap);path=distance_path(s,info)
            end=float(path[1][-1]) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels)
            result=aligned(s,info,path,grid,channels)
            return output({**result,'start_distance_m':start_distance_m,'end_distance_m':end,'resolution_m':resolution_m,
                           'distance_m':grid,'lap_quality':info,'note':'No extrapolation: uncovered distance or timing gaps return null. Units remain producer units; steering is not converted to degrees.'})

    def compare_laps(self, session_id, laps, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=20.0):
        require(isinstance(laps,list) and all(type(n) is int for n in laps) and 2<=len(laps)<=config.MAX_LAPS_PER_REQUEST and len(set(laps))==len(laps),
                'invalid_laps','Compare 2 to 10 distinct lap IDs.')
        channels=['speed','brake','throttle','steering'] if channels is None else channels
        with self.session(session_id) as s:
            infos=[select_lap(s,n) for n in laps]
            require(all(r['benchmark_candidate'] for r in infos),'ineligible_lap','Choose benchmark candidates from list_laps; comparisons exclude incomplete, zero-time, pit, impact and clock-gap intervals.')
            paths=[distance_path(s,r) for r in infos]
            end=min(float(path[1][-1]) for path in paths) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels,len(laps))
            results=[aligned(s,r,path,grid,channels) for r,path in zip(infos,paths)]
            deltas=[]
            for i in range(1,len(results)):
                a,b=results[0],results[i]
                speed_delta=None
                if 'speed' in channels:
                    factor=speed_factor(a['units']['speed'])
                    if factor is not None: speed_delta=(a['channels']['speed']-b['channels']['speed'])*factor
                deltas.append({'lap_a':laps[0],'lap_b':laps[i],'elapsed_delta_a_minus_b_s':a['elapsed_s']-b['elapsed_s'],
                               'speed_delta_a_minus_b_kph':speed_delta,'reported_lap_delta_s':infos[0]['lap_time_s']-infos[i]['lap_time_s']})
            transitions=[control_transitions(s,r,p,start_distance_m,end) for r,p in zip(infos,paths)]
            return output({'distance_m':grid,'resolution_m':resolution_m,'laps':results,'deltas':deltas,
                           'control_onsets':[{'lap':n,**v} for n,v in zip(laps,transitions)],
                           'control_point_differences':[{'lap_a':laps[0],'lap_b':laps[i],**match_onsets(transitions[0],transitions[i])} for i in range(1,len(laps))],
                           'method':'Delta = lap A elapsed time minus B at shared distance crossings; positive means A is slower. Crossing times are interpolated, not official timing deltas. Control onsets are first samples at >=5%, coarsely matched one-to-one within 100 m, not named corners or braking zones. Positive onset-distance difference means A applies the control later along the track.',
                           'conditions':'Same recording/car/layout; fuel, tyres, weather and traffic can still differ. See get_lap_summary condition_context. Official lap validity is unknown.'})
