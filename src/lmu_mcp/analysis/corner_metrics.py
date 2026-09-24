"""Corner ranges and bounded section metrics independent of MCP transport."""
import numpy as np
from ..alignment import aligned, make_grid
from ..database import InspectionError
from ..telemetry import require
from .braking import _clock_gap_between, _distance_at
from .corners import STEERING_THRESHOLD_PCT, detect_corner_ranges
from .summary import speed_factor

CORNER_DETAIL_SPACING_M = 2.0
MAX_CORNER_RANGE_M = 2000.0


def automatic_ranges(session, lap, path):
    steering=session.series('steering')
    lateral=session.series('lateral_acceleration')
    speed=session.series('speed')
    require(steering.unit=='%' and lateral.unit=='G','unknown_corner_unit',
            'Automatic corners require verified steering percent and lateral acceleration G units.')
    factor=speed_factor(speed.unit)
    require(factor is not None,'unknown_speed_unit',
            'Automatic corners require verified speed units of km/h or m/s.')
    first=float(path[1][0]);last=float(path[1][-1])
    resolution=max(5.0,(last-first)/2500.0)
    require(resolution<=20,'corner_limit',
            'Recording is too long for bounded automatic corner detection; use manual ranges.')
    names=['steering','lateral_acceleration','speed']
    grid=make_grid(first,last,resolution,names)
    result=aligned(session,lap,path,grid,names)
    rows=detect_corner_ranges(grid,result['channels']['steering'],
                              result['channels']['lateral_acceleration'],
                              result['channels']['speed']*factor)
    return rows,resolution


def _optional_signal(session,name,unit=None):
    if name not in session.sources:
        return None
    try:
        signal=session.series(name)
        if unit is not None and signal.unit!=unit:
            return None
        return signal
    except InspectionError:
        return None


def _intervention(session,name,signal,start,end):
    if signal is None or start is None or end is None:
        return None,0.0
    inside=(signal.times>start)&(signal.times<end)
    points=np.r_[start,signal.times[inside],end]
    values=session.sample(name,points[:-1])
    durations=np.diff(points)
    covered=np.isfinite(values)&(durations<=signal.max_gap_s)
    return float(durations[covered&(values>0)].sum()),float(durations[covered].sum())


def _brake_point(session,signal,path,lap,start_distance,apex_distance,turn_in_distance):
    if signal is None:
        return None
    times=signal.times
    values=signal.values
    valid=(values[1:]>=5)&(values[:-1]<5)&np.isfinite(values[1:])&np.isfinite(values[:-1])
    valid&=(np.diff(times)<=signal.max_gap_s)
    candidates=[]
    for timestamp in times[1:][valid]:
        if not (lap['start_s']<=timestamp<lap['end_s']):
            continue
        distance=_distance_at(session,path,float(timestamp))
        if distance is not None and max(0,start_distance-250)<=distance<=apex_distance:
            candidates.append(distance)
    if not candidates:
        return None
    before=[distance for distance in candidates if turn_in_distance is not None and distance<=turn_in_distance]
    return float(before[-1] if before else candidates[0])


def corner_metrics(session,lap,path,corner):
    start=float(corner['start_distance_m']);end=float(corner['end_distance_m'])
    require(0<=start<end<=200000 and end-start<=MAX_CORNER_RANGE_M,
            'corner_limit','Corner range must be no longer than 2000 metres and inside 0-200000 m.')
    flags=[]
    names=['speed']
    speed=session.series('speed')
    factor=speed_factor(speed.unit)
    require(factor is not None,'unknown_speed_unit','Corner metrics require verified speed units of km/h or m/s.')
    steering=_optional_signal(session,'steering','%')
    brake=_optional_signal(session,'brake','%')
    throttle=_optional_signal(session,'throttle','%')
    abs_signal=_optional_signal(session,'abs')
    tc_signal=_optional_signal(session,'tc')
    for name,signal in [('steering',steering),('brake',brake),('throttle',throttle)]:
        if signal is not None:
            names.append(name)
    result={**corner,'entry_speed_kph':corner.get('entry_speed_kph'),
            'minimum_speed_kph':corner.get('minimum_speed_kph'),
            'exit_speed_kph':corner.get('exit_speed_kph'),
            'minimum_speed_position_m':None,'brake_point_m':None,
            'turn_in_position_m':None,'throttle_pickup_position_m':None,
            'full_throttle_position_m':None,'section_time_s':None,
            'abs_active_time_s':None,'abs_coverage_s':0.0,
            'tc_active_time_s':None,'tc_coverage_s':0.0,
            'maximum_absolute_steering_pct':None,'mean_absolute_steering_pct':None,
            'quality_flags':flags}
    if start<path[1][0] or end>path[1][-1]:
        flags.append('outside_lap_distance_coverage')
        return result
    grid=make_grid(start,end,CORNER_DETAIL_SPACING_M,names)
    samples=aligned(session,lap,path,grid,names)
    # Include the exact end even if it falls between grid points.
    if grid[-1]<end-1e-8:
        extra=aligned(session,lap,path,np.asarray([end]),names)
        grid=np.r_[grid,end]
        times=np.r_[samples['elapsed_s'],extra['elapsed_s']]+lap['start_s']
        values={name:np.r_[samples['channels'][name],extra['channels'][name]] for name in names}
    else:
        times=samples['elapsed_s']+lap['start_s']
        values=samples['channels']
    speeds=values['speed']*factor
    finite=np.isfinite(speeds)
    if not finite.all() or not np.isfinite(times).all():
        flags.append('incomplete_signal_coverage')
    if not finite.any():
        return result
    minimum_index=int(np.nanargmin(speeds))
    minimum_position=float(grid[minimum_index])
    result['minimum_speed_position_m']=minimum_position
    result['minimum_speed_kph']=float(speeds[minimum_index])
    result['entry_speed_kph']=float(speeds[0]) if np.isfinite(speeds[0]) else None
    result['exit_speed_kph']=float(speeds[-1]) if np.isfinite(speeds[-1]) else None
    if corner['source']=='automatic' or corner.get('apex_distance_m') is None:
        result['apex_distance_m']=minimum_position
    if np.isfinite(times[0]) and np.isfinite(times[-1]) and not _clock_gap_between(session,float(times[0]),float(times[-1])):
        result['section_time_s']=float(times[-1]-times[0])
    else:
        flags.append('clock_gap')
    if steering is not None:
        magnitudes=np.abs(values['steering'])
        good=np.isfinite(magnitudes)
        if good.any():
            result['maximum_absolute_steering_pct']=float(magnitudes[good].max())
            result['mean_absolute_steering_pct']=float(magnitudes[good].mean())
            turn=np.flatnonzero(good&(magnitudes>=STEERING_THRESHOLD_PCT))
            if len(turn):
                result['turn_in_position_m']=float(grid[turn[0]])
    result['brake_point_m']=_brake_point(session,brake,path,lap,start,
                                        result['apex_distance_m'],result['turn_in_position_m'])
    if throttle is not None:
        control=values['throttle']
        after=(grid>=result['apex_distance_m'])&np.isfinite(control)
        pickup=np.flatnonzero(after&(control>=5))
        if len(pickup):
            result['throttle_pickup_position_m']=float(grid[pickup[0]])
            full=np.flatnonzero((np.arange(len(grid))>=pickup[0])&after&(control>=95))
            if len(full):
                result['full_throttle_position_m']=float(grid[full[0]])
    if result['section_time_s'] is not None:
        result['abs_active_time_s'],result['abs_coverage_s']=_intervention(
            session,'abs',abs_signal,float(times[0]),float(times[-1]))
        result['tc_active_time_s'],result['tc_coverage_s']=_intervention(
            session,'tc',tc_signal,float(times[0]),float(times[-1]))
    return result
