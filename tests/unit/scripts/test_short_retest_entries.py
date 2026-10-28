"""First-entry retest watches must use only already completed prices."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_retest_entries import definitions,transform
from short_entry_timing import transform as old_transform


def inputs(values):
    return [dict(at=0,symbol="X",event_id="one",atr=2,probability=.7)],{"X":{i*300000:dict(execution_close=v,entry_open=99999) for i,v in enumerate(values)}}


def run(values,ident="retest_d0.5_b0.5_ttl6",end=None):
    signals,prices=inputs(values)
    return transform(signals,prices,0,end or len(values)*300000,next(s for s in definitions() if s["id"]==ident))


def test_requires_down_bounce_and_failure_on_three_different_bars():
    es,a=run([100,99,100,99.5,98])
    assert es[0]["at"]==900000 and es[0]["atr"]==2
    e=a["events"][0];assert e["down_at"]==300000 and e["bounce_at"]==600000
    assert e["improvement_atr"]==-.25


def test_does_not_short_a_straight_decline_or_unfinished_recovery():
    assert not run([100,99,98,97,96])[0]
    assert not run([100,99,100,101,102])[0]


def test_recovery_uses_running_low_then_running_peak():
    es,a=run([100,99,97,97.5,98,100,99.75,99.5,90])
    assert es[0]["at"]==2100000
    assert a["events"][0]["recovery_low"]==97 and a["events"][0]["recovery_peak"]==100


def test_deadline_and_end_pending_are_distinct():
    assert run([100]*74)[1]["counts"]=={"expired":1}
    assert run([100,99,100,99.5],end=900000)[1]["counts"]=={"end_pending":1}


def test_missing_bar_invalidates_watch_instead_of_skipping_it():
    es,a=run([100,99,float("nan"),100,99.5])
    assert not es and a["counts"]=={"missing_data":1}


def test_trigger_at_exact_expiry_is_allowed_but_not_at_window_end():
    values=[100]*70+[99,100,99.5,99]
    assert run(values)[0][0]["at"]==21600000
    assert not run(values,end=21600000)[0]


def test_future_open_and_future_path_do_not_change_trigger():
    signals,prices=inputs([100,99,100,99.5,90])
    spec=next(s for s in definitions() if s["id"]=="retest_d0.5_b0.5_ttl6")
    a=transform(signals,prices,0,1500000,spec)
    for p in prices["X"].values():p["entry_open"]=-999
    prices["X"][1200000]["execution_close"]=500
    assert transform(signals,prices,0,1500000,spec)==a


def test_untriggered_events_and_source_windows_are_not_silently_dropped():
    signals,prices=inputs([100]*80);signals += [dict(signals[0],event_id="outside",at=-300000)]
    spec=next(s for s in definitions() if s["id"]=="retest_d0.5_b0.5_ttl6")
    es,a=transform(signals,prices,0,24000000,spec)
    assert not es and a["source_events"]==1 and len(a["events"])==1


@pytest.mark.parametrize("ident",["immediate","delay60","breakdown0.5","rejection0.5"])
def test_legacy_controls_preserve_exact_entry_contract(ident):
    args=(*inputs([100,101,102,101.5]+[100]*80),0,84*300000,next(s for s in definitions() if s["id"]==ident))
    assert transform(*args)==old_transform(*args)


@pytest.mark.parametrize("extra",[dict(down_atr=0),dict(bounce_atr=float("nan")),dict(fall_atr=-1),dict(ttl_hours=.0001)])
def test_invalid_parameters_fail_instead_of_creating_false_triggers(extra):
    spec=dict(next(s for s in definitions() if s["mode"]=="retest"),**extra)
    with pytest.raises(ValueError):transform(*inputs([100,99]),0,600000,spec)
