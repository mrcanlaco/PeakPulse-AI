"""SQLite Data Store and State Management for Lightweight Local Shadow Trading."""

from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "shadow_paper"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "shadow_state.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    with get_db_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shadows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            family TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PAUSED', -- 'RUNNING', 'PAUSED', 'STOPPED'
            universe_json TEXT NOT NULL,
            spec_json TEXT NOT NULL,
            initial_capital REAL NOT NULL DEFAULT 10000.0,
            cash REAL NOT NULL DEFAULT 10000.0,
            equity REAL NOT NULL DEFAULT 10000.0,
            realized_pnl REAL NOT NULL DEFAULT 0.0,
            unrealized_pnl REAL NOT NULL DEFAULT 0.0,
            total_trades INTEGER NOT NULL DEFAULT 0,
            win_trades INTEGER NOT NULL DEFAULT 0,
            calmar_benchmark REAL NOT NULL DEFAULT 0.0,
            cagr_benchmark REAL NOT NULL DEFAULT 0.0,
            maxdd_benchmark REAL NOT NULL DEFAULT 0.0,
            created_at REAL NOT NULL,
            last_updated REAL NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            shadow_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side INTEGER NOT NULL DEFAULT 0, -- 1 for Long, -1 for Short, 0 for Flat
            qty REAL NOT NULL DEFAULT 0.0,
            entry_price REAL NOT NULL DEFAULT 0.0,
            mark_price REAL NOT NULL DEFAULT 0.0,
            peak_price REAL NOT NULL DEFAULT 0.0,
            stop_price REAL NOT NULL DEFAULT 0.0,
            unrealized_pnl REAL NOT NULL DEFAULT 0.0,
            unrealized_pnl_pct REAL NOT NULL DEFAULT 0.0,
            opened_at REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (shadow_id, symbol),
            FOREIGN KEY (shadow_id) REFERENCES shadows(id) ON DELETE CASCADE
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shadow_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            pnl REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            fee REAL NOT NULL,
            holding_hours REAL NOT NULL,
            closed_at REAL NOT NULL,
            FOREIGN KEY (shadow_id) REFERENCES shadows(id) ON DELETE CASCADE
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS market_quotes (
            symbol TEXT PRIMARY KEY,
            price REAL NOT NULL,
            funding_rate REAL NOT NULL DEFAULT 0.0,
            updated_at REAL NOT NULL
        )
        """)

        conn.commit()


def register_shadow(
    shadow_id: str,
    name: str,
    family: str,
    universe: List[str],
    spec: dict,
    initial_capital: float = 10_000.0,
    calmar_benchmark: float = 0.0,
    cagr_benchmark: float = 0.0,
    maxdd_benchmark: float = 0.0,
    initial_status: str = "PAUSED",
) -> None:
    now = time.time()
    with get_db_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO shadows (
            id, name, family, status, universe_json, spec_json,
            initial_capital, cash, equity, realized_pnl, unrealized_pnl,
            total_trades, win_trades, calmar_benchmark, cagr_benchmark, maxdd_benchmark,
            created_at, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            shadow_id, name, family, initial_status,
            json.dumps(universe), json.dumps(spec),
            initial_capital, initial_capital, initial_capital, 0.0, 0.0,
            0, 0, calmar_benchmark, cagr_benchmark, maxdd_benchmark,
            now, now,
        ))

        for sym in universe:
            conn.execute("""
            INSERT OR IGNORE INTO positions (shadow_id, symbol, side, qty, entry_price, mark_price, peak_price, stop_price, unrealized_pnl, unrealized_pnl_pct, opened_at)
            VALUES (?, ?, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ?)
            """, (shadow_id, sym, now))

        conn.commit()


def update_shadow_status(shadow_id: str, new_status: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.execute("UPDATE shadows SET status = ?, last_updated = ? WHERE id = ?", (new_status, time.time(), shadow_id))
        conn.commit()
        return cursor.rowcount > 0


def get_all_shadows() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM shadows ORDER BY calmar_benchmark DESC").fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["universe"] = json.loads(item["universe_json"])
            item["spec"] = json.loads(item["spec_json"])
            # Load active positions
            pos_rows = conn.execute("SELECT * FROM positions WHERE shadow_id = ? AND side != 0", (item["id"],)).fetchall()
            item["active_positions"] = [dict(p) for p in pos_rows]
            result.append(item)
        return result


def get_market_quotes() -> Dict[str, Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM market_quotes").fetchall()
        return {r["symbol"]: {"price": r["price"], "funding_rate": r["funding_rate"], "updated_at": r["updated_at"]} for r in rows}


def update_market_quote(symbol: str, price: float, funding_rate: float = 0.0) -> None:
    with get_db_connection() as conn:
        conn.execute("""
        INSERT INTO market_quotes (symbol, price, funding_rate, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET price = excluded.price, funding_rate = excluded.funding_rate, updated_at = excluded.updated_at
        """, (symbol, price, funding_rate, time.time()))
        conn.commit()


init_db()
