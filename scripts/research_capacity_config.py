"""Offline capacity scenarios; production schema remains capped at five."""
from types import SimpleNamespace
from dao_vang.config.settings import ExecutionConfig


def configuration(cap,fee=.0005,slip=20):
    if cap not in [5,10,20,30]:raise ValueError("unregistered_research_capacity")
    settings=ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip).model_dump()
    return SimpleNamespace(**dict(settings,max_open_positions=cap))
