"""Shadow feed / replay / dashboard behaviour (no network)."""

from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd
import pytest

from dao_vang.nostop.engine import cost_matrix
from dao_vang.nostop.shadow.book import shadow_state
from dao_vang.nostop.shadow.feed import BAR_MS, FUND_MS, SharedFeed
from dao_vang.nostop.shadow.store import Store
from dao_vang.nostop.shadow.web import make_server, overview
from dao_vang.nostop.signals import Ctx

from .test_nostop import make_panel

SPEC = {
    "family": "composite",
    "params": {"factors": "taker7+fund7", "q": 0.2, "K": 20, "rebal": 1, "mode": "ls", "tv": 0.3, "buffer": 0.1},
}


class FakeClient:
    def __init__(self, symbols, funding=0.0001):
        self.symbols = symbols
        self.calls = {"klines": 0, "premium": 0, "funding_history": 0}
        self.funding = funding
        self.next_funding_offset = 0

    @staticmethod
    def _px(t_ms: int, j: int) -> float:
        return 100.0 + j + ((t_ms // BAR_MS) % 40) * 0.1

    def klines(self, symbol, start_ms, limit):
        self.calls["klines"] += 1
        j = self.symbols.index(symbol)
        rows, t = [], (start_ms // BAR_MS) * BAR_MS
        for _ in range(limit):
            o = self._px(t, j)
            rows.append([t, str(o), str(o * 1.01), str(o * 0.99), str(o * 1.002), "1000", t + BAR_MS - 1,
                         str(o * 1000), 10, "500", "0", "0"])
            t += BAR_MS
            if t > self.now_ms:
                break
        return rows

    def premium_all(self):
        self.calls["premium"] += 1
        nxt = (self.now_ms // FUND_MS + 1) * FUND_MS + self.next_funding_offset
        return [{"symbol": s, "lastFundingRate": str(self.funding), "nextFundingTime": nxt} for s in self.symbols]

    def funding_history(self, symbol, start_ms, limit=1000):
        self.calls["funding_history"] += 1
        t = (start_ms // FUND_MS + 1) * FUND_MS
        out = []
        while t <= self.now_ms - 60_000:
            out.append({"fundingTime": t + 3, "fundingRate": str(self.funding)})
            t += FUND_MS
        return out


def _seed(tmp_path, n_days=520):
    p = make_panel(n_days=n_days)
    seed = tmp_path / "seed.npz"
    np.savez_compressed(
        seed,
        index=p.index.as_unit("ns").asi8,
        symbols=np.array(p.symbols),
        **{k: getattr(p, k) for k in ("open", "high", "low", "close", "qvol", "taker", "volume", "funding")},
    )
    return p, seed


def _feed(tmp_path, p, seed, client):
    f = SharedFeed(tmp_path / "d", client, window=5000, seed_path=seed)
    f.load()
    return f


def test_sync_adds_closed_bars_and_a_forming_bar_with_only_its_open(tmp_path):
    p, seed = _seed(tmp_path)
    c = FakeClient(p.symbols)
    f = _feed(tmp_path, p, seed, c)
    last_seed = int(f.index[-1])
    c.now_ms = last_seed + int(3.5 * BAR_MS)
    f.sync(c.now_ms)
    assert int(f.index[-1]) == last_seed + 3 * BAR_MS
    assert np.isfinite(f.a["close"][-3]).all() and np.isfinite(f.a["close"][-2]).all()
    assert np.isnan(f.a["close"][-1]).all() and np.isfinite(f.a["open"][-1]).all()
    panel, closed = f.panel()
    assert closed == len(f.index) - 2
    assert np.array_equal(panel.close[-1], panel.open[-1])  # flat placeholder, not data
    assert np.isnan(f.a["close"][-1]).all()  # feed itself is untouched by the placeholder


def test_steady_state_cost_is_one_kline_call_per_symbol_and_one_funding_call(tmp_path):
    p, seed = _seed(tmp_path)
    c = FakeClient(p.symbols)
    f = _feed(tmp_path, p, seed, c)
    c.now_ms = int(f.index[-1]) + BAR_MS + 25_000
    f.sync(c.now_ms)
    for k in c.calls:
        c.calls[k] = 0
    c.now_ms += BAR_MS  # one more bar, one more 8h settlement every second bar
    f.sync(c.now_ms)
    assert c.calls["klines"] == len(p.symbols)
    assert c.calls["funding_history"] == 0
    assert c.calls["premium"] <= 1


def test_funding_uses_premium_index_for_one_missing_settlement_and_history_for_many(tmp_path):
    p, seed = _seed(tmp_path)
    c = FakeClient(p.symbols, funding=0.0003)
    f = _feed(tmp_path, p, seed, c)
    base = int(f.funding_through)
    c.now_ms = base + FUND_MS + 120_000
    f.sync(c.now_ms)
    assert c.calls["premium"] == 1 and c.calls["funding_history"] == 0
    row = int((base + FUND_MS - f.index[0]) // BAR_MS)
    assert np.allclose(f.funding[row], 0.0003)
    c.calls["premium"] = 0
    c.now_ms = base + 6 * FUND_MS + 120_000  # five settlements missed -> history path
    f.sync(c.now_ms)
    assert c.calls["funding_history"] == len(p.symbols)
    assert f.funding_through == base + 6 * FUND_MS
    assert np.allclose(f.funding[int((base + 5 * FUND_MS - f.index[0]) // BAR_MS)], 0.0003)


def test_wrong_funding_cycle_in_premium_index_is_not_trusted(tmp_path):
    p, seed = _seed(tmp_path)
    c = FakeClient(p.symbols, funding=0.0009)
    c.next_funding_offset = 3 * 3600 * 1000  # exchange reports an unexpected cycle
    f = _feed(tmp_path, p, seed, c)
    c.now_ms = int(f.funding_through) + FUND_MS + 120_000
    f.sync(c.now_ms)
    assert c.calls["funding_history"] == len(p.symbols)  # fell back to per-symbol history


def test_shadow_opens_the_last_decision_at_start_only_when_asked():
    full = make_panel()
    start = 350 * 6 + 2  # 08:00 bar: not a decision bar, last decision was earlier
    cut = start + 2  # window = the start bar plus one more bar
    p = type(full)(
        full.index[:cut], full.symbols,
        *(getattr(full, f)[:cut] for f in ("open", "high", "low", "close", "qvol", "taker", "volume", "funding")),
    )
    ctx, cost = Ctx(p), cost_matrix(p)
    inv = shadow_state(p, ctx, cost, SPEC, start, 1000.0, init_target=True)
    flat = shadow_state(p, ctx, cost, SPEC, start, 1000.0, init_target=False)
    assert inv["n_positions"] > 0 and inv["trades"]
    assert {t["t"] for t in inv["trades"]} == {inv["start_ts"]}  # opened at the start bar's open
    assert inv["fees"] > 0 and inv["equity"] < 1000.0 + 50  # opening costs were paid
    assert flat["n_positions"] == 0 and not flat["trades"]  # waits for its own first decision
    assert flat["equity"] == 1000.0



def test_shadow_history_is_causal_and_ignores_decisions_before_its_start():
    full = make_panel()
    cut = 400 * 6
    short = type(full)(
        full.index[:cut], full.symbols,
        *(getattr(full, f)[:cut] for f in ("open", "high", "low", "close", "qvol", "taker", "volume", "funding")),
    )
    start = 330 * 6
    a = shadow_state(short, Ctx(short), cost_matrix(short), SPEC, start, 1000.0)
    b = shadow_state(full, Ctx(full), cost_matrix(full), SPEC, start, 1000.0)
    ta = dict((t, e) for t, e in a["curve"])
    tb = dict((t, e) for t, e in b["curve"])
    common = [t for t in ta if t in tb and t < a["asof_ts"] - 2 * BAR_MS // 1]
    assert len(common) > 20
    assert all(abs(ta[t] - tb[t]) < 1e-6 for t in common)
    assert a["trades"] and min(t["t"] for t in a["trades"]) >= a["start_ts"]
    # equity starts exactly at capital: nothing happened before the shadow existed
    assert a["curve"][0][1] == 1000.0


def test_dashboard_overview_live_mark_and_stale_and_pause_roundtrip(tmp_path):
    st = Store(tmp_path)
    st.add("s1", SPEC, 0, 1000.0, {"val_calmar": 2.0, "test_calmar": 3.0})
    st.write_state("s1", {
        "equity": 1010.0, "pnl_today": 5.0, "max_dd": 0.02, "n_positions": 1, "gross": 1.0, "net": 0.1,
        "days": 3.0, "asof_ts": 1_000, "positions": [
            {"symbol": "BTCUSDT", "side": "SHORT", "notional": -500.0, "open_price": 100.0,
             "avg_entry": 100.0, "qty": -5.0}],
        "trades": [], "curve": [[0, 1000.0], [1000, 1010.0]], "capital": 1000.0, "start_ts": 0,
    })
    st.write_json("prices.json", {"ts": 1, "prices": {"BTCUSDT": 102.0}})
    o = overview(st, now_ms=1_000 + 2 * BAR_MS)
    row = o["shadows"][0]
    assert row["equity"] == pytest.approx(1010.0 - 10.0)  # short -500 notional, +2% price
    assert row["stale"] is True
    assert o["totals"]["positions"] == 1

    srv = make_server("127.0.0.1", 0, tmp_path)
    import threading

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        data = json.loads(urllib.request.urlopen(base + "/api/overview").read())
        assert data["shadows"][0]["id"] == "s1"
        req = urllib.request.Request(base + "/api/shadow/s1/pause", method="POST")
        assert json.loads(urllib.request.urlopen(req).read())["ok"] is True
        assert st.shadows()[0]["status"] == "paused"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/shadow/..%2F..%2Fsecret")
        assert e.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as e2:
            urllib.request.urlopen(urllib.request.Request(base + "/api/shadow/nope/pause", method="POST"))
        assert e2.value.code == 404
    finally:
        srv.shutdown()


def test_spec_ids_registered_once(tmp_path):
    st = Store(tmp_path)
    assert st.add("a", SPEC, 0, 1.0, {}) is True
    assert st.add("a", SPEC, 0, 1.0, {}) is False
    assert pd.Timestamp(0, unit="ms").year == 1970


def test_profile_text_matches_the_locked_code_not_marketing():
    from dao_vang.nostop.shadow.profiles import alpha_rationale, mechanism
    from dao_vang.nostop.shadow.store import describe_spec

    base = {"factors": "taker7+fund14", "q": 0.15, "K": 40, "rebal": 3, "mode": "ls", "tv": 0.3, "buffer": 0.1}
    eq = {"family": "composite", "params": base}
    iv = {"family": "composite", "params": {**base, "wt": "ivol"}}
    assert "chia đều" in mechanism(eq)[0] and "NGHỊCH" not in mechanism(eq)[0]
    assert "NGHỊCH" in mechanism(iv)[0] and "chia đều" not in mechanism(iv)[0]
    assert describe_spec(iv).endswith("ivol") and not describe_spec(eq).endswith("ivol")
    text = " ".join(alpha_rationale(eq))
    assert "KHÔNG phải trung hòa beta" in text and "GIẢ THUYẾT" in text
    assert not any(w in text for w in ("an toàn", "thông minh", "thuần túy", "triệt tiêu"))
