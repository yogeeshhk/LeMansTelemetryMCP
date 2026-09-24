"""Direct Python coaching API; database connections live for one request only."""
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import json
import math
import numpy as np
from . import config
from .database import Repository, InspectionError, inspect_connection
from .cache import AnalysisCache
from .telemetry import Session, require
from .analysis.laps import identify_laps, select_lap
from .analysis.summary import lap_summary, speed_factor, control_transitions, match_onsets
from .analysis.braking import BrakingSettings, build_braking_zones, match_positions
from dataclasses import asdict
from .alignment import distance_path, make_grid, aligned, validate_grid_request


def _distance_digits(resolution):
    if not isinstance(resolution, (int, float)) or not math.isfinite(resolution):
        return 1
    return min(4, max(1, -Decimal(str(resolution)).as_tuple().exponent))


def serializable(value, field=None, unit=None, distance_digits=1):
    """Round only the wire representation; analysis arrays retain full precision."""
    if isinstance(value, Decimal):
        return serializable(float(value), field, unit, distance_digits)
    if isinstance(value, np.ndarray):
        return serializable(value.tolist(), field, unit, distance_digits)
    if isinstance(value, np.generic):
        return serializable(value.item(), field, unit, distance_digits)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if field in ('resolution_m', 'start_distance_m', 'end_distance_m'):
            digits = 4
        elif (field and field.endswith('_kph')) or (unit == 'km/h' and field not in ('frequency_hz',)):
            digits = 1
        elif (field and field.endswith('_s')) or unit == 's':
            digits = 3
        elif (field and field.endswith('_m')) or unit == 'm':
            digits = distance_digits
        elif unit == '%':
            digits = 3
        elif field and field.endswith('_pct'):
            digits = 1
        else:
            digits = 4
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        own_unit = value.get('unit', unit)
        own_digits = _distance_digits(value['resolution_m']) if 'resolution_m' in value else distance_digits
        units = value.get('units', {})
        result = {}
        for key, item in value.items():
            if key == 'channels' and isinstance(item, dict) and isinstance(units, dict):
                result[key] = {name: serializable(array, name, units.get(name), own_digits)
                               for name, array in item.items()}
            else:
                result[str(key)] = serializable(item, key, own_unit, own_digits)
        return result
    if isinstance(value, (list, tuple)):
        return [serializable(item, field, unit, distance_digits) for item in value]
    return value


def output(value):
    result=serializable(value)
    require(len(json.dumps(result,allow_nan=False).encode('utf-8'))<=config.MAX_OUTPUT_BYTES,
            'response_limit','Response is too large; request fewer channels/laps, a smaller range or coarser resolution.')
    return result


class TelemetryService:
    def __init__(self, repository=None):
        self.repository=repository or Repository()
        self.cache=AnalysisCache()

    @contextmanager
    def session(self, session_id):
        require(isinstance(session_id,str) and 0<len(session_id)<=512,'invalid_session','Use a session ID from list_sessions.')
        with self.repository.open(session_id) as c:
            revision=self.repository.revision(session_id)
            self.cache.activate(session_id,revision)
            inspection_settings=(config.MAX_TABLES,config.MAX_CATALOG_ROWS)
            inspection=self.cache.get(session_id,revision,'inspection',inspection_settings)
            if inspection is None:
                inspection=inspect_connection(c,session_id)
                self.cache.put(session_id,revision,'inspection',inspection,inspection_settings)
            session=Session(c,inspection)
            session.cache_revision=revision
            yield session

    def _laps(self, session):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        rows=self.cache.get(session_id,revision,'laps',settings)
        if rows is None:
            rows=identify_laps(session)
            self.cache.put(session_id,revision,'laps',rows,settings)
        return rows

    def _select_lap(self, session, number):
        return select_lap(session,number,self._laps(session))

    def _path(self, session, lap):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        path=self.cache.get(session_id,revision,'distance_path',lap['lap'],settings)
        if path is None:
            path=distance_path(session,lap)
            self.cache.put(session_id,revision,'distance_path',path,lap['lap'],settings)
        return path

    def _aligned(self, session, lap, path, grid, channels, start, end, resolution):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        settings=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        parts=(lap['lap'],tuple(channels),start,end,resolution,settings)
        result=self.cache.get(session_id,revision,'aligned',*parts)
        if result is None:
            result=aligned(session,lap,path,grid,channels)
            self.cache.put(session_id,revision,'aligned',result,*parts)
        return result

    def _braking_zones(self, session, lap, settings):
        session_id=session.inspection.session_id
        revision=session.cache_revision
        budget=(config.MAX_SOURCE_SAMPLES,config.MAX_TOTAL_SOURCE_SAMPLES)
        cached=self.cache.get(session_id,revision,'braking_zones',lap['lap'],settings,budget)
        if cached is None:
            cached=build_braking_zones(session,lap,self._path(session,lap),settings)
            self.cache.put(session_id,revision,'braking_zones',cached,lap['lap'],settings,budget)
        return cached

    def get_braking_zones(self, session_id, lap, onset_pct=10.0, release_pct=5.0,
                          min_duration_s=0.3, min_peak_pct=20.0, min_speed_drop_kph=5.0):
        settings=BrakingSettings(onset_pct,release_pct,min_duration_s,min_peak_pct,
                                 min_speed_drop_kph).validate()
        with self.session(session_id) as session:
            selected=self._select_lap(session,lap)
            result=self._braking_zones(session,selected,settings)
            return output({'session_id':session_id,'lap':lap,'lap_quality':selected,
                           'thresholds':asdict(settings),**result,
                           'method':'Native brake samples use onset/release hysteresis; events need minimum duration, peak and speed drop. Distance uses the validated monotonic lap path. No large clock/source gaps are bridged. ABS is positive-state time over covered intervals. Throttle pickup is the first >=5% sample within 5 s and 250 m after release, before the next brake interval. Incomplete onset/release is flagged.'})

    def compare_braking_zones(self, session_id, lap_a, lap_b, onset_pct=10.0,
                              release_pct=5.0, min_duration_s=0.3, min_peak_pct=20.0,
                              min_speed_drop_kph=5.0, max_match_distance_m=100.0):
        settings=BrakingSettings(onset_pct,release_pct,min_duration_s,min_peak_pct,
                                 min_speed_drop_kph).validate()
        require(type(lap_a) is int and type(lap_b) is int and lap_a>0 and lap_b>0 and lap_a!=lap_b,
                'invalid_laps','Choose two distinct positive lap IDs from list_laps.')
        require(type(max_match_distance_m) in (int,float) and math.isfinite(max_match_distance_m)
                and 10<=max_match_distance_m<=300,'invalid_match_range',
                'Use max_match_distance_m from 10 to 300 metres.')
        with self.session(session_id) as session:
            first=self._select_lap(session,lap_a)
            second=self._select_lap(session,lap_b)
            require(first['benchmark_candidate'] and second['benchmark_candidate'],
                    'ineligible_lap','Choose benchmark candidates from list_laps for braking-zone comparison.')
            result_a=self._braking_zones(session,first,settings)
            result_b=self._braking_zones(session,second,settings)
            eligible_a=[z for z in result_a['zones'] if not z['quality_flags']]
            eligible_b=[z for z in result_b['zones'] if not z['quality_flags']]
            pairs,unmatched_a,unmatched_b=match_positions(eligible_a,eligible_b,max_match_distance_m)
            def delta(a,b,key):
                left,right=a[key],b[key]
                return left-right if left is not None and right is not None else None
            matches=[]
            for i,j in pairs:
                a,b=eligible_a[i],eligible_b[j]
                matches.append({'zone_a':a['zone'],'zone_b':b['zone'],
                                'a':a,'b':b,
                                'a_minus_b':{
                                    'brake_start_m':delta(a,b,'start_distance_m'),
                                    'braking_distance_m':delta(a,b,'braking_distance_m'),
                                    'initial_speed_kph':delta(a,b,'initial_speed_kph'),
                                    'minimum_speed_kph':delta(a,b,'minimum_speed_kph'),
                                    'peak_brake_pct':delta(a,b,'peak_brake_pct'),
                                    'brake_release_m':delta(a,b,'end_distance_m'),
                                    'throttle_pickup_m':delta(a,b,'throttle_pickup_distance_m'),
                                    'abs_active_time_s':delta(a,b,'abs_active_time_s')}})
            return output({'session_id':session_id,'lap_a':lap_a,'lap_b':lap_b,
                           'thresholds':asdict(settings),'max_match_distance_m':max_match_distance_m,
                           'matches':matches,'unmatched_zone_ids_a':[eligible_a[i]['zone'] for i in unmatched_a],
                           'unmatched_zone_ids_b':[eligible_b[j]['zone'] for j in unmatched_b],
                           'excluded_partial_zone_ids_a':[z['zone'] for z in result_a['zones'] if z['quality_flags']],
                           'excluded_partial_zone_ids_b':[z['zone'] for z in result_b['zones'] if z['quality_flags']],
                           'excluded_intervals_a':result_a['excluded_intervals'],
                           'excluded_intervals_b':result_b['excluded_intervals'],
                           'warnings_a':result_a['warnings'],'warnings_b':result_b['warnings'],
                           'note':'Matches maximize count then minimize start-position distance without crossing zone order. A-minus-B is first lap minus second in stated units. Unmatched or partial zones are not silently paired; measured differences do not establish a driving cause.'})

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
            try: duration=float(s.clock[-1]-s.clock[0]);laps=self._laps(s)
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
            laps=self._laps(s)
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
        with self.session(session_id) as s: return output(lap_summary(s,self._select_lap(s,lap)))

    def get_telemetry(self, session_id, lap, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=2.0):
        channels=['speed','brake','throttle','steering','gear'] if channels is None else channels
        validate_grid_request(start_distance_m,end_distance_m,resolution_m,channels)
        with self.session(session_id) as s:
            info=self._select_lap(s,lap);path=self._path(s,info)
            end=float(path[1][-1]) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels)
            result=self._aligned(s,info,path,grid,channels,start_distance_m,end,resolution_m)
            return output({**result,'start_distance_m':start_distance_m,'end_distance_m':end,'resolution_m':resolution_m,
                           'distance_m':grid,'lap_quality':info,'note':'No extrapolation: uncovered distance or timing gaps return null. Units remain producer units; steering is not converted to degrees.'})

    def compare_laps(self, session_id, laps, channels=None, start_distance_m=0.0, end_distance_m=None, resolution_m=20.0):
        require(isinstance(laps,list) and all(type(n) is int for n in laps) and 2<=len(laps)<=config.MAX_LAPS_PER_REQUEST and len(set(laps))==len(laps),
                'invalid_laps','Compare 2 to 10 distinct lap IDs.')
        channels=['speed','brake','throttle','steering'] if channels is None else channels
        validate_grid_request(start_distance_m,end_distance_m,resolution_m,channels,len(laps))
        with self.session(session_id) as s:
            infos=[self._select_lap(s,n) for n in laps]
            require(all(r['benchmark_candidate'] for r in infos),'ineligible_lap','Choose benchmark candidates from list_laps; comparisons exclude incomplete, zero-time, pit, impact and clock-gap intervals.')
            paths=[self._path(s,r) for r in infos]
            end=min(float(path[1][-1]) for path in paths) if end_distance_m is None else end_distance_m
            grid=make_grid(start_distance_m,end,resolution_m,channels,len(laps))
            results=[self._aligned(s,r,path,grid,channels,start_distance_m,end,resolution_m) for r,path in zip(infos,paths)]
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
