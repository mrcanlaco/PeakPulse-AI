"""CLI: manage and run the local no-stop shadows.

    python -m dao_vang.nostop.shadow add --passing            # all locked candidates > 1 in train/val/test
    python -m dao_vang.nostop.shadow add --ids composite-2a753a0b,composite-3db01c74
    python -m dao_vang.nostop.shadow list
    python -m dao_vang.nostop.shadow pause|resume|stop <id|*>
    python -m dao_vang.nostop.shadow run [--port 8890]       # feed + engine + dashboard in ONE process
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

import pandas as pd

from ..data import OUT_DIR
from ..registry import load_lock
from .binance import ApiError, PublicClient
from .feed import BAR_MS
from .runner import ShadowRunner
from .store import DATA_DIR, Store
from .web import make_server


def _research_metrics() -> dict:
    df = pd.read_csv(OUT_DIR / "final_results.csv").set_index("id")
    out = {}
    for sid, r in df.iterrows():
        out[sid] = {
            "train_calmar": round(float(r.train_calmar), 3),
            "val_calmar": round(float(r.val_calmar), 3),
            "test_calmar": round(float(r.test_calmar), 3),
            "test_total_return": round(float(r.test_total_return), 4),
        }
    return out


def cmd_add(args) -> None:
    lock = load_lock()
    research = _research_metrics()
    specs = {s["id"]: {"family": s["family"], "params": s["params"]} for s in lock["specs"]}
    if args.ids:
        ids = args.ids.split(",")
    else:
        ids = [
            i for i, m in research.items()
            if m["train_calmar"] > 1 and m["val_calmar"] > 1 and m["test_calmar"] > 1
        ]
    client = PublicClient()
    try:
        client.sync_time()
    except ApiError:
        pass
    start_ms = client.now_ms() // BAR_MS * BAR_MS
    store = Store(DATA_DIR)
    added = 0
    for sid in ids:
        if sid not in specs:
            raise SystemExit(f"{sid} is not a locked candidate")
        added += store.add(sid, specs[sid], start_ms, args.capital, research[sid])
    print(f"added {added} shadow(s); start bar {pd.Timestamp(start_ms, unit='ms', tz='UTC')}")
    print(f"wrote {_write_profiles()} profiles")


def _write_profiles() -> int:
    from .profiles import build_profiles

    profiles = build_profiles()
    Store(DATA_DIR).write_profiles(profiles)
    return len(profiles)


def cmd_profiles(_args) -> None:
    print(f"wrote {_write_profiles()} profiles")


def cmd_list(_args) -> None:
    for s in Store(DATA_DIR).shadows():
        print(f"{s['id']:<24} {s['status']:<8} cap {s['capital']:>9.0f}  {s['desc']}")


def cmd_set(args) -> None:
    status = {"pause": "paused", "resume": "running", "stop": "stopped"}[args.cmd]
    print("ok" if Store(DATA_DIR).set_status(args.id, status) else "unknown id")


def cmd_run(args) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    runner = ShadowRunner(DATA_DIR)
    srv = make_server(args.host, args.port, DATA_DIR)
    threading.Thread(target=srv.serve_forever, daemon=True, name="shadow-web").start()
    print(f"dashboard http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    t = threading.Thread(target=runner.run_forever, daemon=True, name="shadow-runner")
    t.start()
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        runner.stop.set()
        srv.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(prog="dao_vang.nostop.shadow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--ids", default="")
    a.add_argument("--passing", action="store_true")
    a.add_argument("--capital", type=float, default=10000.0)
    a.set_defaults(fn=cmd_add)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("profiles", help="rebuild per-shadow descriptions").set_defaults(fn=cmd_profiles)
    for c in ("pause", "resume", "stop"):
        p = sub.add_parser(c)
        p.add_argument("id")
        p.set_defaults(fn=cmd_set)
    r = sub.add_parser("run")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8890)
    r.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
