"""Freeze the diagnostic candidate before evaluating another date range."""

import json

import pandas as pd
from compare_account_risk import ROOT,sha,write
from search_guard_ablation import OUT


def main():
    target=OUT/"candidate_freeze.json"
    if target.exists():raise RuntimeError("candidate_already_frozen_do_not_overwrite")
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    candidates=[s for s in summary["specs"] if s["guard"]["mask"] in [0,2,15]]
    write(target,dict(frozen_at=pd.Timestamp.now(tz="UTC").isoformat(),
        purpose="Fixed diagnostic evaluation on a subsequent date range; no live promotion or claim of50%monthly.",
        primary_mask=2,controls=[0,15],primary_notional=25,hypothetical_notional=100,
        source=summary["protocol"]["source"]["entry"]["source"],specs=candidates,
        original_universe_manifest_sha256=summary["protocol"]["data_sha256"],
        selection_history="Chosen after repeated inspection of2025-09..2026-05. Later history may already have been studied for other strategies; disclose reuse, never call it pristine OOS without evidence.",
        evaluation_rules="Keep original frozen30coin universe, all eligible signals, same fees/funding/MTM/cap/leverage. Verify5m mark/trade/funding coverage first; missing symbols/data fail acceptance rather than disappear. Include nofilter/fullguard controls at25/100notional. No parameter adjustment based on subsequent results.",
        target="Each consecutive month>=50%netmarkedgrowth; profitable total/rolling quarters do not satisfy goal.",
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["short_multitimeframe_signals.py","short_guard_ablation.py","short_entry_guards.py","short_funding_flow_signals.py","account_scaled_replay.py"]},
        financial_verification=False,live_config_changed=False))
    print(target)


if __name__=="__main__":main()
