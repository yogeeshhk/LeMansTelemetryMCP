"""Distance crossings and bounded grids without sorting away reversals or gaps."""
import math
import numpy as np
from . import config
from .telemetry import require


def distance_path(session, lap):
    signal=session.series('lap_distance')
    require(signal.unit=='m','unknown_distance_unit','Lap distance must have verified metre units.')
    inside=(signal.times>=lap['start_s'])&(signal.times<lap['end_s'])
    times,distances=signal.times[inside],signal.values[inside]
    require(len(times)>=2 and np.isfinite(distances).all(),'distance_coverage','Lap has insufficient finite distance samples.')
    # Explicitly discard one stale pre-line sample only at a detected wrap very near the boundary.
    if distances[0]>100 and distances[1]<10 and times[1]-lap['start_s']<.5:
        times,distances=times[1:],distances[1:]
    require(len(times)>=2 and (np.diff(distances)>=0).all(),'distance_reversal','Lap distance reverses or wraps within the interval; choose another lap or inspect its quality flags.')
    require(distances[-1]>distances[0],'distance_coverage','Lap has no forward distance coverage.')
    return times,distances,signal.max_gap_s


def make_grid(start, end, resolution, channels, lap_count=1):
    require(all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (start,end,resolution)),
            'invalid_range','Distance and resolution must be finite numbers.')
    require(0<=start<end<=200000,'invalid_range','Use 0 <= start_distance_m < end_distance_m <= 200000.')
    require(resolution>=config.MIN_RESOLUTION_M,'query_limit','Increase resolution_m to at least 0.1 m.')
    require(isinstance(channels,list) and all(isinstance(c,str) for c in channels) and 1<=len(channels)<=config.MAX_CHANNELS and len(set(channels))==len(channels),
            'query_limit','Request 1 to 20 distinct channels.')
    require(all(isinstance(c,str) and 0<len(c)<=128 for c in channels),'invalid_channel','Channel names must be nonempty strings of at most 128 characters.')
    require(resolution>=1 or end-start<=config.MAX_DISTANCE_RANGE_HIGH_RES_M,'query_limit','For sub-metre resolution, query at most 2000 metres at a time.')
    count=math.floor((end-start)/resolution+1e-8)+1
    cells=count*(lap_count*(len(channels)+1)+1+(2*(lap_count-1) if lap_count>1 else 0))
    require(count<=config.MAX_OUTPUT_SAMPLES and cells<=config.MAX_OUTPUT_VALUES,'query_limit',
            'Request fewer channels/laps, a shorter distance range, or increase resolution_m (coarser spacing). Maximum 5000 points and 20000 total numeric values.')
    return float(start)+np.arange(count,dtype=float)*float(resolution)


def crossing_times(path, grid, session):
    times,distances,gap_limit=path
    right=np.searchsorted(distances,grid,side='left')
    safe=np.clip(right,0,len(distances)-1)
    exact=(right<len(distances))&np.isclose(distances[safe],grid,rtol=0,atol=1e-9)
    result=np.full(grid.shape,np.nan)
    result[exact]=times[safe[exact]]
    left=np.maximum(safe-1,0)
    delta=distances[safe]-distances[left]
    valid=(right>0)&(right<len(distances))&(~exact)&(delta>0)&((times[safe]-times[left])<=gap_limit)
    fraction=np.divide(grid-distances[left],delta,out=np.zeros_like(grid),where=delta>0)
    result[valid]=times[left[valid]]+fraction[valid]*(times[safe[valid]]-times[left[valid]])
    result[session.in_clock_gap(result)]=np.nan
    return result


def aligned(session, lap, path, grid, channels):
    times=crossing_times(path,grid,session)
    values={};units={};methods={};timing={}
    for name in channels:
        signal=session.series(name)
        values[name]=session.sample(name,times)
        units[name]=signal.unit
        methods[name]='previous state hold' if signal.discrete else 'linear in time at interpolated distance crossing'
        timing[name]=signal.timing
    return {'lap':lap['lap'],'elapsed_s':times-lap['start_s'],'channels':values,'units':units,
            'interpolation':methods,'timing':timing,'missing_crossings':int(np.isnan(times).sum()),
            'coverage_m':[float(path[1][0]),float(path[1][-1])]}
