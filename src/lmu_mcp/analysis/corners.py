"""Approximate corner ranges from verified distance-aligned signals."""
import math
import numpy as np
from ..telemetry import require

STEERING_THRESHOLD_PCT = 8.0
LATERAL_THRESHOLD_G = 0.15
MIN_ACTIVE_LENGTH_M = 25.0
MAX_HOLE_M = 15.0
PADDING_M = 10.0
MAX_CORNERS = 128


def detect_corner_ranges(distance_m, steering_pct, lateral_g, speed_kph):
    """Require sustained steering and lateral load; speed locates an approximate apex."""
    distance = np.asarray(distance_m,dtype=float)
    steering = np.asarray(steering_pct,dtype=float)
    lateral = np.asarray(lateral_g,dtype=float)
    speed = np.asarray(speed_kph,dtype=float)
    require(all(array.ndim==1 and len(array)==len(distance) for array in (steering,lateral,speed))
            and len(distance)>=2 and np.isfinite(distance).all() and (np.diff(distance)>0).all(),
            'invalid_corner_samples','Corner inputs require matching one-dimensional signals and increasing finite distances.')
    step=float(np.median(np.diff(distance)))
    require(math.isfinite(step) and 0<step<=20,'invalid_corner_samples',
            'Corner distance spacing must be positive and at most 20 metres.')
    valid=np.isfinite(steering)&np.isfinite(lateral)&np.isfinite(speed)
    active=valid&(np.abs(steering)>=STEERING_THRESHOLD_PCT)&(np.abs(lateral)>=LATERAL_THRESHOLD_G)&(speed>=10)
    # Join only short, fully observed holes surrounded by active samples.
    filled=active.copy()
    index=0
    while index<len(active):
        if active[index]:
            index+=1
            continue
        end=index
        while end<len(active) and not active[end]:
            end+=1
        if index>0 and end<len(active) and active[index-1] and active[end]:
            hole_length=float(distance[end]-distance[index-1]-step)
            if hole_length<=MAX_HOLE_M and valid[index:end].all():
                filled[index:end]=True
        index=end
    starts=np.flatnonzero(np.diff(np.r_[False,filled].astype(int))==1)
    ends=np.flatnonzero(np.diff(np.r_[filled,False].astype(int))==-1)
    ranges=[]
    for start,end in zip(starts,ends):
        if distance[end]-distance[start]+step < MIN_ACTIVE_LENGTH_M:
            continue
        left=start
        while left>0 and valid[left-1] and distance[start]-distance[left-1]<=PADDING_M:
            left-=1
        right=end
        while right+1<len(distance) and valid[right+1] and distance[right+1]-distance[end]<=PADDING_M:
            right+=1
        if ranges and left<=ranges[-1][1]:
            ranges[-1]=(ranges[-1][0],max(right,ranges[-1][1]))
        else:
            ranges.append((left,right))
        require(len(ranges)<=MAX_CORNERS,'corner_limit',
                'Too many automatic corner ranges; inspect the signal mapping or use manual definitions.')
    result=[]
    for corner_id,(left,right) in enumerate(ranges,1):
        local=speed[left:right+1]
        apex=left+int(np.argmin(local))
        result.append({'corner_id':corner_id,'name':None,'source':'automatic',
                       'start_distance_m':float(distance[left]),
                       'apex_distance_m':float(distance[apex]),
                       'end_distance_m':float(distance[right]),
                       'entry_speed_kph':float(speed[left]),
                       'minimum_speed_kph':float(speed[apex]),
                       'exit_speed_kph':float(speed[right])})
    return result
