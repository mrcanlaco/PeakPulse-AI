"""Trade an hourly shock in the latest completed daily trend direction."""
from collections import Counter
import hashlib

from shock_weekly_alignment import classify


MODES = ['weekly_sign', 'anti_sign', 'weekly_extreme', 'anti_extreme']


def opposite(side):
    if side == 'LONG':return 'SHORT'
    if side == 'SHORT':return 'LONG'
    raise ValueError('invalid_side')


def transform(events, state, mode):
    if mode not in MODES:raise ValueError('invalid_direction_mode')
    output=[];counts=Counter();decisions=[]
    for event in events:
        d=classify(event,state)
        side=None
        if d['reason']=='ready':
            if mode.endswith('extreme'):
                side=d['weekly_side']
            else:
                side='LONG' if d['raw168']>0 else 'SHORT' if d['raw168']<0 else None
            if side is not None and mode.startswith('anti_'):
                side=opposite(side)
        reason=d['reason'] if d['reason']!='ready' else 'no_direction' if side is None else 'accepted'
        counts[reason]+=1
        decisions.append({**d,'event_id':event['event_id'],'at':event['at'],
                          'symbol':event['symbol'],'hourly_side':event['side'],
                          'direction_mode':mode,'selected_side':side,'reason':reason})
        if side is not None:
            emitted=dict(event,side=side,origin_event_id=event['event_id'])
            emitted['event_id']=hashlib.sha256(
                f"shock_weekly_direction:{mode}:{event['event_id']}:{side}".encode()).hexdigest()[:24]
            output.append(emitted)
    return output,dict(counts),decisions
