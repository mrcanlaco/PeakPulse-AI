"""Point-in-time signal scheduling and open-only entry quote admission.

No trade outcome, future OHLC, fee, funding or portfolio state is consumed.
Monthly membership is the independently verified historical PIT schedule;
live construction of that schedule remains a separate upstream service.
"""
from collections import Counter
from copy import deepcopy
import math
import pandas as pd

FIVE_MINUTES = pd.Timedelta(minutes=5)


def utc(value):
    t=pd.Timestamp(value)
    if t.tzinfo is None:
        raise ValueError('Timezone-aware timestamps are required')
    return t.tz_convert('UTC')


class DecisionFeed:
    def __init__(self,membership,events,start,end):
        self.membership={month:{row['symbol'] for row in rows} for month,rows in membership.items()}
        self.events=deepcopy(events)
        self.start,self.end=utc(start),utc(end)
        self.pending={}
        self.seen=set()
        self.counts=Counter()
        self.receipts=[]

    def _known_closure(self,symbol,at):
        for e in self.events:
            if e['symbol']!=symbol or at<utc(e['known_from_utc']):continue
            cutoff=utc(e['entry_close_only_from'] or e['settlement_at'])
            if at>=cutoff and (not e.get('relaunch_at') or at<utc(e['relaunch_at'])):
                return e
        return None

    def signal(self,snapshot,*,as_of,past_hour_opens):
        t=utc(as_of)
        if t!=t.floor('h') or utc(snapshot['decision_time'])!=t:
            raise ValueError('Signal must belong to this completed H1 timestamp')
        if any(k.startswith(('sim_','future_','exit_')) or k in ('paths','pnl','gross_return','net_return') for k in snapshot):
            raise ValueError('Future outcomes are forbidden in a signal snapshot')
        symbol,tf=snapshot['symbol'],snapshot['tf']
        if tf not in ('4h','1d'):
            raise ValueError('Unsupported signal timeframe')
        due=t+FIVE_MINUTES
        cid=f'{symbol}:{tf}:{int(due.timestamp())}'
        if cid in self.seen:raise ValueError('Duplicate signal identity')
        history=pd.DatetimeIndex(past_hour_opens)
        if len(history) and (history.tz is None or (history+pd.Timedelta(hours=1)>t).any()):
            raise ValueError('Future or unclosed H1 history')
        self.seen.add(cid)
        reason=None
        annual_end=pd.Timestamp(year=due.year+1,month=1,day=1,tz='UTC')
        if not self.start<=due<min(self.end,annual_end)-pd.Timedelta(days=5):
            reason='outside_annual_entry_window'
        elif symbol not in self.membership.get(t.strftime('%Y-%m'),set()):
            reason='not_monthly_member'
        elif 'm6_f4_expanded' not in snapshot['eligible_milestones']:
            reason='not_m6_expanded'
        elif len(history)!=24 or not history.as_unit('ns').equals(pd.date_range(t-pd.Timedelta(hours=24),periods=24,freq='h').as_unit('ns')):
            reason='incomplete_past_24h'
        if reason:
            self.counts[reason]+=1
            self.receipts.append({'id':cid,'decision_time':t.isoformat(),'status':reason})
            return None
        item={'id':cid,'symbol':symbol,'tf':tf,'wave_key':snapshot['wave_key'],
            'decision_ts':int(t.timestamp()),'entry_ts':int(due.timestamp()),
            'stop':float(snapshot['sl_m6']),'targets':[float(snapshot[k]) for k in ('tp1','tp2','tp3')],
            'score':float(snapshot['full_conviction_score']),'milestones':list(snapshot['eligible_milestones'])}
        if not all(math.isfinite(x) for x in [item['stop'],item['score'],*item['targets']]) or min(item['stop'],*item['targets'])<=0:
            raise ValueError('Invalid predeclared trade geometry')
        self.pending[cid]=item
        self.counts['scheduled']+=1
        return cid

    def entry_open(self,cid,*,as_of,quote):
        item=self.pending[cid]
        t=utc(as_of)
        if t!=pd.Timestamp(item['entry_ts'],unit='s',tz='UTC'):
            raise ValueError('Only the scheduled entry timestamp is allowed')
        if quote is not None:
            if set(quote)!={'symbol','open_time_ms','open'}:
                raise ValueError('Entry quote must contain only the current open, not future OHLC')
            if quote['symbol']!=item['symbol'] or quote['open_time_ms']!=item['entry_ts']*1000:
                raise ValueError('Wrong or future entry quote')
            if not math.isfinite(quote['open']) or quote['open']<=0:
                raise ValueError('Invalid entry open')
        reason=None
        closure=self._known_closure(item['symbol'],t)
        if closure is not None:reason='known_close_only_or_settlement'
        elif quote is None:reason='missing_scheduled_entry_quote'
        elif not item['stop']>quote['open']>item['targets'][0]>item['targets'][1]>item['targets'][2]>0:
            reason='gap_invalidated_ladder'
        del self.pending[cid]
        if reason:
            self.counts[reason]+=1
            self.receipts.append({'id':cid,'entry_time':t.isoformat(),'status':reason})
            return None
        output={**item,'entry':float(quote['open'])}
        self.counts['entry_proposal']+=1
        self.receipts.append({'id':cid,'entry_time':t.isoformat(),'status':'entry_proposal',
                              'membership_month':t.strftime('%Y-%m'),'known_lifecycle_allowed':True})
        return output
