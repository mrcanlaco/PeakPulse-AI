"""Light-weight local shadow paper trading for the locked no-stop candidates.

One process, one shared market feed, one pass of feature computation per bar:
    feed.py    shared 4h panel (seeded from research data, then public Binance klines)
    book.py    deterministic replay of one candidate from its start bar
    runner.py  scheduler (bar close + 60s price poll), writes state/*.json
    web.py     local dashboard
"""
