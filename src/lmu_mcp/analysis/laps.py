"""Lap completion boundaries with recorded validity kept separate from eligibility."""
import numpy as np
from ..telemetry import require


def identify_laps(session):
    series=session.series('lap_number')
    require(len(series.times)>0,'missing_laps','No lap-counter samples were recorded.')
    require(np.isfinite(series.values).all() and (series.values>=0).all() and (series.values==np.floor(series.values)).all(),
            'invalid_laps','Lap counter must contain nonnegative integers.')
    changes=np.r_[True,np.diff(series.values)!=0]
    times,counts=series.times[changes],series.values[changes]
    require(len(times)<=1001,'lap_limit','Recording contains too many lap boundaries for this request.')
    rows=[]
    start=float(max(times[0],session.clock[0]))
    for i in range(1,len(times)):
        end=float(times[i]); increment=counts[i]-counts[i-1]
        # A reset or jump closes a partial interval, rather than silently merging laps.
        completed=increment==1
        reported=session.event('Lap Time',end) if completed else None
        reported=reported if reported is not None and reported>0 else None
        flags=[]
        inferred_start=False
        if i==1 and reported is not None:
            candidate=end-reported
            if candidate>=start-.05:
                start=candidate; inferred_start=True
        if not completed: flags.append('counter_reset_or_jump')
        if reported is None: flags.append('missing_recorded_lap_time')
        if i==1 and not inferred_start: flags.append('first_interval_start_unverified')
        if start<session.clock[0]-.05 or end>session.clock[-1]+.05: flags.append('incomplete_recording')
        if reported and abs(end-start-reported)>.15: flags.append('lap_clock_disagreement')
        for name,flag in [('In Pits','pit_lane'),('LastImpactMagnitude','impact_event')]:
            if name not in session.sources: continue
            event=session.series(name)
            inside=(event.times>start)&(event.times<end)
            occurred=bool(np.any(event.values[inside]>0))
            if name=='In Pits': occurred |= bool(session.event(name,start))
            if occurred: flags.append(flag)
        if session.event('Finish Status',start): flags.append('post_finish')
        gap=np.diff(session.clock)
        if np.any((gap>session.clock_gap_limit)&(session.clock[:-1]<end)&(session.clock[1:]>start)):
            flags.append('clock_gap')
        s1=session.event('Last Sector1',end);s12=session.event('Last Sector2',end)
        sectors=[s1,s12-s1,reported-s12] if reported and s1 and s12 and 0<s1<s12<reported else None
        rows.append({'lap':len(rows)+1,'recorded_lap_number':int(counts[i]) if completed else None,
                     'start_s':start,'end_s':end,'lap_time_s':reported,'boundary_duration_s':end-start,
                     'complete':completed,'valid':None,'benchmark_candidate':not flags,'flags':flags,
                     'sector_times_s':sectors,'start_inferred_from_reported_time':inferred_start})
        start=end
    if session.clock[-1]>start:
        rows.append({'lap':len(rows)+1,'recorded_lap_number':None,'start_s':start,'end_s':float(session.clock[-1]),
                     'lap_time_s':None,'boundary_duration_s':float(session.clock[-1]-start),'complete':False,'valid':None,
                     'benchmark_candidate':False,'flags':['incomplete_final_interval'],'sector_times_s':None,
                     'start_inferred_from_reported_time':False})
    return rows


def select_lap(session, number, rows=None):
    require(type(number) is int and number>0,'invalid_lap','Choose a positive lap ID from list_laps.')
    rows=identify_laps(session) if rows is None else rows
    row=next((row for row in rows if row['lap']==number),None)
    require(row is not None,'unknown_lap','Lap ID is not present in this recording.')
    return row
