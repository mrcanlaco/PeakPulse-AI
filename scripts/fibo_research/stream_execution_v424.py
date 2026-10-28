"""Sequential short portfolio driven by observed bars, funding and entry quotes.

No trade path, exit timestamp or future return is accepted. One complete batch
per timestamp is required: funding, closed bars, then ranked entry proposals.
The caller must attest that the funding feed is complete through that time.
This module submits no orders and performs no market-data downloads.
"""
from collections import Counter
from copy import deepcopy
import math

BAR_MS = 300_000
HOUR_MS = 3_600_000
ENTRY_KEYS = {'id','symbol','tf','wave_key','decision_ts_ms','entry_ts_ms','entry',
              'stop','targets','score','milestones'}


def fill(side, reference, qty, scenario):
    price = reference * (1 + (-1 if side == 'SELL' else 1) * scenario['slippage_bps']/10000)
    value = price*qty
    return {'side': side, 'reference_price': reference, 'execution_price': price,
            'qty': qty, 'notional': value, 'fee': value*scenario['fee_bps']/10000,
            'slippage_cost': qty*abs(price-reference)}


def stop_loss(entry, stop, scenario):
    a, b = fill('SELL',entry,1.,scenario), fill('BUY',stop,1.,scenario)
    return b['execution_price']-a['execution_price']+a['fee']+b['fee']


class SequentialPortfolio:
    def __init__(self, start_ms, end_ms, policy, scenario):
        if not isinstance(start_ms,int) or not isinstance(end_ms,int) or end_ms <= start_ms:
            raise ValueError('Invalid evaluation boundaries')
        if policy['sizing'] not in ('fixed','risk') or policy.get('hours') not in (None,24):
            raise ValueError('Unsupported sizing or holding horizon')
        if policy['gate'] not in ('expanded','elite_sniper','sniper'):
            raise ValueError('Unsupported policy gate')
        if set(scenario) != {'fee_bps','slippage_bps'} or not all(math.isfinite(x) and x >= 0 for x in scenario.values()) or scenario['slippage_bps'] >= 10000:
            raise ValueError('Invalid execution cost scenario')
        self.start, self.end = start_ms, end_ms
        self.policy, self.scenario = deepcopy(policy), deepcopy(scenario)
        self.clock = start_ms-1
        self.equity = 100.
        self.positions, self.internal = {}, {}
        self.ledger, self.curve = [], [(start_ms,100.)]
        self.waves, self.cooldown = set(), {}
        self.rejected, self.filtered = Counter(), Counter()
        self.seen_ids, self.execution_issues = set(), []

    def _gate(self,c):
        milestones = c['milestones']
        if 'm6_f4_expanded' not in milestones:
            return False
        gate = self.policy['gate']
        if gate == 'elite_sniper' and 'm6_f4_elite_sniper' not in milestones:
            return False
        if (gate == 'sniper' or self.policy.get('hours') == 24) and 'm6_f4_sniper' not in milestones:
            return False
        if 'rr_min' in self.policy:
            return (c['entry']-c['targets'][0])/(c['stop']-c['entry']) >= self.policy['rr_min']
        return True

    def _validate(self,t,entries,bars,funding,watermark):
        if not isinstance(t,int) or not self.clock < t <= self.end or t < self.start:
            raise ValueError('Timestamp must advance once per complete batch')
        if watermark != t:
            raise ValueError('Funding feed completeness through this timestamp is required')
        ids = [c['id'] for c in entries]
        if len(set(ids)) != len(ids) or any(cid in self.seen_ids for cid in ids):
            raise ValueError('Duplicate entry proposal id')
        for c in entries:
            if set(c) != ENTRY_KEYS:
                raise ValueError('Only current signal/entry fields are accepted; future outcome fields are forbidden')
            if c['tf'] not in ('4h','1d') or c['entry_ts_ms'] != t or c['decision_ts_ms']+BAR_MS != t:
                raise ValueError('Entry must follow the decision by five minutes')
            if t % BAR_MS or not all(math.isfinite(x) for x in [c['entry'],c['stop'],c['score'],*c['targets']]) or len(c['targets']) != 3:
                raise ValueError('Invalid entry prices or time grid')
            if min(c['entry'],c['stop'],*c['targets']) <= 0:
                raise ValueError('Nonpositive entry/ladder price')
        for symbol,bar in bars.items():
            if set(bar) != {'open_time_ms','open','high','low','close','volume'} or bar['open_time_ms']+BAR_MS != t:
                raise ValueError('Only the bar closing now is permitted')
            if bar['open_time_ms'] % BAR_MS or not all(math.isfinite(bar[k]) for k in ('open','high','low','close','volume')):
                raise ValueError('Invalid observed candle')
            if bar['volume'] < 0 or bar['low'] <= 0 or bar['high'] < max(bar['open'],bar['close'],bar['low']) or bar['low'] > min(bar['open'],bar['close']):
                raise ValueError('Invalid OHLCV ordering')
        for p in self.positions.values():
            due = self.internal[p['id']]['next_close_ms']
            if t > due or (t == due and p['symbol'] not in bars):
                raise ValueError('Missing required execution bar; do not impute or advance')
        symbols = set()
        for symbol,event in funding:
            if symbol in symbols or event['funding_ts_ms'] != t:
                raise ValueError('Duplicate or mistimed funding event')
            symbols.add(symbol)
            if not math.isfinite(event['funding_rate']) or not math.isfinite(event['mark_price']) or event['mark_price'] <= 0:
                raise ValueError('Invalid funding rate/mark')
            if not event.get('price_source'):
                raise ValueError('Funding mark provenance is required')
            if event.get('mark_reference_ts_ms', t) > t:
                raise ValueError('Future funding mark is forbidden')

    def _bar(self,p,bar,t):
        c = self.internal[p['id']]
        entry, rem, active = p['entry'], p['rem'], p['active']
        realized, hits, targets = c['realized'], c['hits'], c['targets']
        before = rem
        old_total = c['gross_total']
        previous_mark = p['mark']
        done, reason = False, None
        if bar['high'] >= active:
            realized += rem*(entry-max(active,bar['open']))/entry
            rem, done = 0., True
            reason = 'stop' if not hits[0] else 'ratchet'
        if not done:
            for j,target in enumerate(targets):
                if hits[j] or bar['low'] > target:
                    continue
                weight = min((.5,.3,.2)[j],rem)
                realized += weight*(entry-target)/entry
                rem -= weight
                hits[j] = True
                if rem < 1e-12:
                    rem, done, reason = 0., True, f'tp{j+1}'
                    break
                active = entry if j == 0 else targets[0]
                if bar['high'] >= active:
                    realized += rem*(entry-active)/entry
                    rem, done, reason = 0., True, 'ratchet'
                    break
        if not done and t == c['deadline_ms']:
            realized += rem*(entry-bar['close'])/entry
            rem, done = 0., True
            reason = 'horizon24' if self.policy.get('hours') == 24 else 'horizon'
        total = realized + rem*(entry-bar['close'])/entry
        delta = total-old_total
        closed = before-rem
        change = p['reference_notional']*delta
        if closed > 1e-10:
            reference = (before*previous_mark-rem*bar['close']-delta*entry)/closed
            out = fill('BUY',reference,p['qty']*closed,self.scenario)
            out.update(timestamp_ms=t,aggregation='quantity_weighted_exit_group_within_5m')
            p['fills'].append(out)
            change -= out['fee']+out['slippage_cost']
            p['fees'] += out['fee']; p['slippage'] += out['slippage_cost']
            if bar['volume'] == 0:
                self.execution_issues.append({'id':p['id'],'timestamp_ms':t,'kind':'zero_volume_exit'})
        self.equity += change; p['pnl'] += change
        p.update(rem=rem,mark=bar['close'],active=active)
        c.update(realized=realized,gross_total=total,next_close_ms=t+BAR_MS)
        if done:
            p.update(exit_ts_ms=t,exit_reason=reason,gross_reference_return=realized)
            self.ledger.append(p)
            key = (p['symbol'],p['tf'])
            self.cooldown[key] = max(self.cooldown[key],t)
            del self.positions[p['id']]
            del self.internal[p['id']]

    def process(self,t,*,entries=(),bars=None,funding=(),funding_complete_through_ms=None):
        bars = bars or {}
        entries, funding = list(entries), list(funding)
        self._validate(t,entries,bars,funding,funding_complete_through_ms)
        self.clock = t
        changed = False
        by_symbol = dict(funding)
        for p in list(self.positions.values()):
            if p['symbol'] in by_symbol:
                event = by_symbol[p['symbol']]
                amount = p['qty']*p['rem']*event['mark_price']*event['funding_rate']
                p['funding_events'].append({**event,'remaining_qty':p['qty']*p['rem'],'cashflow':amount})
                p['funding'] += amount; p['pnl'] += amount; self.equity += amount
                changed = True
        for p in list(self.positions.values()):
            if self.internal[p['id']]['next_close_ms'] == t:
                self._bar(p,bars[p['symbol']],t)
                changed = True
        if changed:
            self.curve.append((t,self.equity))
        for c in sorted(entries,key=lambda a:(-a['score'],a['symbol'],a['tf'])):
            self.seen_ids.add(c['id'])
            if not c['stop'] > c['entry'] > c['targets'][0] > c['targets'][1] > c['targets'][2] > 0:
                self.filtered['gap_invalidated_ladder'] += 1; continue
            if not self._gate(c) or t >= self.end-5*24*HOUR_MS:
                self.filtered['policy_or_boundary'] += 1; continue
            key = (c['symbol'],c['tf']); wave = (*key,c['wave_key'])
            if wave in self.waves or t < self.cooldown.get(key,0) or any((p['symbol'],p['tf']) == key for p in self.positions.values()):
                self.rejected['wave_or_cooldown'] += 1; continue
            if self.equity <= 0:
                self.rejected['insolvent'] += 1; continue
            qty = .20*self.equity/c['entry']
            loss = stop_loss(c['entry'],c['stop'],self.scenario)
            if self.policy['sizing'] == 'risk':
                qty = min(qty,.005*self.equity/loss)
            initial = fill('SELL',c['entry'],qty,self.scenario)
            cost = initial['fee']+initial['slippage_cost']
            after = self.equity-cost
            notional = sum(p['qty']*p['rem']*max(p['entry'],p['mark']) for p in self.positions.values())
            risk = 0.
            for p in self.positions.values():
                at_stop = fill('BUY',p['active'],p['qty']*p['rem'],self.scenario)
                risk += max(0.,at_stop['notional']-p['qty']*p['rem']*min(p['entry'],p['mark'])+at_stop['fee'])
            cap = .12 if self.policy['sizing'] == 'fixed' else .02
            if len(self.positions) >= 5 or notional+qty*c['entry'] > after+1e-9 or risk+qty*loss > after*cap+1e-9:
                self.rejected['portfolio_cap'] += 1; continue
            initial.update(timestamp_ms=t,aggregation='single_entry')
            p = {'id':c['id'],'symbol':c['symbol'],'tf':c['tf'],'entry_ts_ms':t,'entry':c['entry'],'stop':c['stop'],
                'qty':qty,'reference_notional':qty*c['entry'],'equity_at_entry':self.equity,'rem':1.,'mark':c['entry'],'active':c['stop'],
                'pnl':-cost,'fees':initial['fee'],'slippage':initial['slippage_cost'],'funding':0.,'fills':[initial],
                'funding_events':[],'missing_execution_bars':0,'stop_risk_with_execution_costs':qty*loss}
            horizon = self.policy.get('hours',72 if c['tf'] == '4h' else 120)
            deadline = min(self.end,t+horizon*HOUR_MS)
            self.internal[c['id']] = {'targets':list(c['targets']),'hits':[False]*3,'realized':0.,'gross_total':0.,
                                      'next_close_ms':t+BAR_MS,'deadline_ms':deadline}
            self.positions[c['id']] = p
            self.waves.add(wave); self.cooldown[key] = t+4*HOUR_MS
            self.equity = after; self.curve.append((t,self.equity))

    def finish(self):
        if self.positions:
            raise ValueError('Unclosed positions; future bars must not be invented')
        if self.clock != self.end:
            raise ValueError('The evaluation boundary has not been processed')
        curve = [*self.curve,(self.end,self.equity)]
        peak,dd = curve[0][1],0.
        for _,value in curve:
            peak = max(peak,value); dd = max(dd,1-value/peak)
        metric = {'return_pct':self.equity-100,'max_dd_pct':dd*100,'trades':len(self.ledger),
            'rejected':dict(self.rejected),'fees_pct':sum(p['fees'] for p in self.ledger),
            'slippage_pct':sum(p['slippage'] for p in self.ledger),'funding_pct':sum(p['funding'] for p in self.ledger),
            'gross_reference_pnl_pct':sum(p['reference_notional']*p['gross_reference_return'] for p in self.ledger)}
        assert abs(self.equity-100-sum(p['pnl'] for p in self.ledger)) < 1e-7
        return {'metric':metric,'ledger':deepcopy(self.ledger),'curve':curve,'execution_issues':deepcopy(self.execution_issues)}

    def state(self):
        """JSON-safe state for a completed timestamp batch; no hidden event queue."""
        data = deepcopy(self.__dict__)
        data.update(version=1,waves=[list(a) for a in sorted(self.waves)],
                    cooldown=[[list(k),v] for k,v in sorted(self.cooldown.items())],
                    seen_ids=sorted(self.seen_ids),rejected=dict(self.rejected),filtered=dict(self.filtered))
        return data

    @classmethod
    def restore(cls,data):
        data = deepcopy(data)
        if data.pop('version') != 1:
            raise ValueError('Unsupported state version')
        obj = cls(data['start'],data['end'],data['policy'],data['scenario'])
        data['waves'] = {tuple(a) for a in data['waves']}
        data['cooldown'] = {tuple(k):v for k,v in data['cooldown']}
        data['seen_ids'] = set(data['seen_ids'])
        data['rejected'] = Counter(data['rejected']); data['filtered'] = Counter(data['filtered'])
        data['curve'] = [tuple(a) for a in data['curve']]
        obj.__dict__.update(data)
        return obj
