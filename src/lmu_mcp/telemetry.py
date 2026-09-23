"""Time-domain telemetry access independent of MCP and tool response formatting."""
from dataclasses import dataclass
import numpy as np
from .database import InspectionError, SignalReader
from .models import Source
from .schema import numeric


@dataclass
class Series:
    times: np.ndarray
    values: np.ndarray
    unit: str | None
    discrete: bool
    max_gap_s: float
    timing: str


def require(condition, code, message):
    if not condition:
        raise InspectionError(code, message)


class Session:
    def __init__(self, connection, inspection):
        self.inspection = inspection
        self.reader = SignalReader(connection, inspection)
        self.metadata = self.reader.metadata()
        self.cache = {}
        self._clock = None
        self.sources = {name: src for name,src in inspection.channels.channels.items() if src is not None}
        for name,info in inspection.catalog.items():
            table = next((t for t in inspection.tables if (t.schema,t.name,t.kind)==('main',name,'BASE TABLE')),None)
            if table is None: continue
            cols={c.name for c in table.columns}
            values=tuple(n for n in ('value','value1','value2','value3','value4') if n in cols)
            if values not in [('value',),('value1','value2','value3','value4')]: continue
            if not all(numeric(c) for c in table.columns if c.name in values): continue
            if info['kind']=='event' and 'ts' not in cols: continue
            self.sources.setdefault(name,Source('main',name,values,'ts' if info['kind']=='event' else None,
                                                info['kind'],info['unit'],info['frequency_hz']))

    def source(self, name):
        require(name in self.sources,'missing_channel',f'Channel {name!r} is absent or ambiguous. Use list_channels for supported names.')
        return self.sources[name]

    @property
    def clock(self):
        if self._clock is None:
            source=self.source('timestamp')
            require(source.unit=='s','unknown_time_unit','Clock units must be verified as seconds before time-based analysis.')
            values=self.reader.values(source)[:,0]
            require(len(values)>=2 and np.isfinite(values).all() and (np.diff(values)>0).all(),
                    'invalid_clock','Recording clock must contain finite strictly increasing timestamps.')
            self._clock=values
        return self._clock

    @property
    def clock_gap_limit(self):
        return float(np.median(np.diff(self.clock))*1.5+1e-8)

    def in_clock_gap(self, query):
        idx=np.searchsorted(self.clock,query,side='right')-1
        valid=(idx>=0)&(idx<len(self.clock)-1)
        lo=np.clip(idx,0,len(self.clock)-2)
        return valid & (query>self.clock[lo]+1e-8) & ((self.clock[lo+1]-self.clock[lo])>self.clock_gap_limit)

    def series(self, selector):
        if selector in self.cache: return self.cache[selector]
        name,sep,component=selector.rpartition(':')
        name,component=(name,component) if sep else (selector,None)
        source=self.source(name)
        require(component is not None or len(source.value_columns)==1,'component_required',f'{name} has multiple components. Select :value1 through :value4 as listed by list_channels.')
        component=component or source.value_columns[0]
        require(component in source.value_columns,'unknown_component','Unknown signal component.')
        if name=='timestamp':
            series=Series(self.clock,self.clock,'s',False,self.clock_gap_limit,'recorded')
        else:
            columns=((source.timestamp_column,) if source.timestamp_column else ())+ (component,)
            data=self.reader.values(source,columns)
            table=next(t for t in self.inspection.tables if (t.schema,t.name)==(source.schema,source.table))
            dtype=next(c.data_type for c in table.columns if c.name==component)
            discrete=source.kind=='event' or dtype=='BOOLEAN' or name in ('gear','lap_number','abs','tc')
            if source.timestamp_column:
                times,values=data[:,0],data[:,1]
                require(np.isfinite(times).all() and (np.diff(times)>=0).all(),'invalid_clock','Signal event timestamps are invalid or reversed.')
                # At a repeated timestamp the last recorded state wins.
                keep=np.r_[np.diff(times)>0,True] if len(times) else np.array([],dtype=bool)
                times,values=times[keep],values[keep]
                limit=float('inf') if source.kind=='event' else self.clock_gap_limit
                timing='recorded event timestamp' if source.kind=='event' else 'recorded timestamp'
            else:
                base=self.source('timestamp').frequency_hz
                hz=source.frequency_hz
                require(base is not None and hz is not None and hz>0 and base>=hz and float(base/hz).is_integer(),
                        'unsupported_timing',f'{name}: sample frequency does not support an integer clock stride; refusing inferred timing.')
                times=self.clock[::int(base/hz)]
                values=data[:,0]
                require(len(times)==len(values),'sample_count_mismatch',f'{name}: sample count does not match its clock stride.')
                limit=1.5/hz+1e-8
                timing='inferred from GPS clock row order and frequency ratio; sample phase is unverified'
            series=Series(times,values,source.unit,discrete,limit,timing)
        self.cache[selector]=series
        return series

    def sample(self, selector, query):
        series=self.series(selector)
        query=np.asarray(query,dtype=float)
        result=np.full(query.shape,np.nan)
        if not len(series.times): return result
        idx=np.searchsorted(series.times,query,side='right')-1
        valid=(idx>=0)&(query<=self.clock[-1]+1e-8)
        left=np.clip(idx,0,len(series.times)-1)
        if series.discrete:
            valid &= (query-series.times[left] <= series.max_gap_s)
            result[valid]=series.values[left[valid]]
        else:
            right=np.minimum(left+1,len(series.times)-1)
            exact=np.isclose(query,series.times[left],rtol=0,atol=1e-8)
            gap=series.times[right]-series.times[left]
            between=valid & (right>left) & (gap<=series.max_gap_s) & (query<=series.times[right])
            fraction=np.divide(query-series.times[left],gap,out=np.zeros_like(query),where=gap>0)
            result[between]=series.values[left[between]]+(series.values[right[between]]-series.values[left[between]])*fraction[between]
            result[valid&exact]=series.values[left[valid&exact]]
        result[self.in_clock_gap(query)]=np.nan
        return result

    def event(self, name, time):
        if name not in self.sources: return None
        value=self.sample(name,[time])[0]
        return float(value) if np.isfinite(value) else None
