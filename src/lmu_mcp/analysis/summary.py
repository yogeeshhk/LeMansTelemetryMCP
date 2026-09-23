"""Time-weighted compact metrics and basic control transitions (not corner zones)."""
import numpy as np
from ..database import InspectionError


def speed_factor(unit):
    return 1.0 if unit=='km/h' else 3.6 if unit=='m/s' else None


def lap_summary(session, lap):
    times=session.clock[(session.clock>=lap['start_s'])&(session.clock<lap['end_s'])]
    times=np.unique(np.r_[lap['start_s'],times])
    durations=np.diff(np.r_[times,lap['end_s']])
    valid_time=(durations>0)&(durations<=session.clock_gap_limit)
    warnings=[]; sampled={}
    def values(name,unit=None):
        try:
            signal=session.series(name)
            if unit is not None and signal.unit!=unit:
                warnings.append(f'{name}: expected {unit}; metric unavailable.')
                return None
            result=session.sample(name,times)
            sampled[name]=result
            return result
        except InspectionError as e:
            warnings.append(f'{name}: {e.code}')
            return None
    result={**lap,'sample_count':len(times)}
    speed=values('speed')
    factor=speed_factor(session.series('speed').unit) if speed is not None else None
    if speed is not None and factor is not None:
        good=np.isfinite(speed)&valid_time
        total=float(durations[good].sum())
        result.update({'max_speed_kph':float(np.max(speed[good])*factor) if good.any() else None,
                       'min_speed_kph':float(np.min(speed[good])*factor) if good.any() else None,
                       'average_speed_kph':float(np.sum(speed[good]*durations[good])/total*factor) if total else None,
                       'speed_coverage_s':total})
    else:
        result.update(max_speed_kph=None,min_speed_kph=None,average_speed_kph=None,speed_coverage_s=0)
        if speed is not None: warnings.append('speed: unknown physical units')
    throttle=values('throttle','%');brake=values('brake','%')
    for name,array in [('throttle',throttle),('braking',brake)]:
        good=np.isfinite(array)&valid_time if array is not None else np.zeros(len(times),dtype=bool)
        coverage=float(durations[good].sum())
        result[name+'_time_pct']=float(durations[good&(array>=5)].sum()/coverage*100) if coverage else None
        result[name+'_coverage_s']=coverage
    if throttle is not None and brake is not None:
        good=np.isfinite(throttle)&np.isfinite(brake)&valid_time
        coverage=float(durations[good].sum())
        result['coasting_time_pct']=float(durations[good&(throttle<5)&(brake<5)].sum()/coverage*100) if coverage else None
        result['coasting_coverage_s']=coverage
    else: result.update(coasting_time_pct=None,coasting_coverage_s=0)
    for name in ['abs','tc']:
        array=values(name)
        if array is None:
            result[name]={'activation_count':None,'active_time_s':None,'coverage_s':0}
            continue
        good=np.isfinite(array)&valid_time;active=good&(array>0)
        transitions=active[1:] & (~active[:-1]) & good[:-1]
        result[name]={'activation_count':int(transitions.sum()),'active_time_s':float(durations[active].sum()),
                      'active_at_start':bool(active[0]) if len(active) else None,'coverage_s':float(durations[good].sum())}
    gear=values('gear')
    result['gear_changes']=int(np.count_nonzero((np.diff(gear)!=0)&np.isfinite(gear[:-1])&np.isfinite(gear[1:])&valid_time[:-1])) if gear is not None else None
    result['braking_events']=None
    if brake is not None:
        active=np.isfinite(brake)&(brake>=5)&valid_time
        edges=np.diff(np.r_[False,active,False].astype(int))
        result['braking_events']=sum(float(durations[a:b].sum())>=.15 for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)))
    # Useful fuel/tyre context, preserving producer units and component indices.
    result['condition_context']={}
    for name in ['Fuel Level','tyre_wear','tyre_pressure','tyre_temperature']:
        if name not in session.sources: continue
        source=session.source(name)
        components={}
        for component in source.value_columns:
            selector=name if len(source.value_columns)==1 else name+':'+component
            data=values(selector)
            good=np.isfinite(data)&valid_time if data is not None else np.zeros(len(times),dtype=bool)
            if good.any():
                components[component]={'first':float(data[good][0]),'last':float(data[good][-1]),'min':float(data[good].min()),'max':float(data[good].max())}
        result['condition_context'][name]={'unit':source.unit,'components':components}
    result['warnings']=warnings
    result['method']='Time-weighted on recorded clock intervals; controls use >=5% thresholds; brake applications must last >=0.15s. Gaps are excluded and coverage reported. Counts exclude an already-active initial state. Official validity remains unknown.'
    return result


def control_transitions(session, lap, path, start, end):
    """Raw threshold crossings for coarse comparisons, not matched braking zones."""
    output={}
    for name in ['brake','throttle']:
        try:
            signal=session.series(name)
            if signal.unit!='%':
                output[name]=None;continue
        except InspectionError:
            output[name]=None;continue
        inside=(signal.times>=lap['start_s'])&(signal.times<lap['end_s'])
        ts,vs=signal.times[inside],signal.values[inside]
        mask=(vs[1:]>=5)&(vs[:-1]<5)&np.isfinite(vs[1:])&np.isfinite(vs[:-1])&(np.diff(ts)<=signal.max_gap_s)
        events=ts[1:][mask]
        # Linear distance sampling is supported only inside the validated monotonic lap path.
        distances=np.interp(events,path[0],path[1],left=np.nan,right=np.nan)
        good=(distances>=start)&(distances<=end)
        selected=[float(d) for d in distances[good]]
        output[name]={'distances_m':selected[:50],'total':len(selected),'truncated':len(selected)>50}
    return output


def match_onsets(a, b):
    result={}
    for channel in ['brake','throttle']:
        if a[channel] is None or b[channel] is None:
            result[channel]=None;continue
        left=a[channel]['distances_m'];right=b[channel]['distances_m']
        unused=set(range(len(right)));matches=[]
        for distance in left:
            if not unused: break
            nearest=min(unused,key=lambda j:abs(right[j]-distance))
            if abs(right[nearest]-distance)<=100:
                matches.append({'a_distance_m':distance,'b_distance_m':right[nearest],
                                'a_minus_b_m':distance-right[nearest]})
                unused.remove(nearest)
        result[channel]={'matches':matches,'unmatched_a':len(left)-len(matches),'unmatched_b':len(unused),
                         'input_truncated':a[channel]['truncated'] or b[channel]['truncated']}
    return result
