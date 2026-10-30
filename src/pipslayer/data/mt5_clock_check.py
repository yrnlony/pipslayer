"""Read-only, non-conclusive MT5 clock/timestamp diagnostic."""
from __future__ import annotations
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from typing import Any

from .mt5_adapter import MT5_TIMEFRAMES, _rate_field

ALLOWED_CALLS = frozenset({"initialize", "symbol_select", "symbol_info_tick", "copy_rates_from_pos", "shutdown", "last_error"})
CANDIDATES = ("pc_clock_is_accurate", "broker_bar_boundaries_are_utc", "broker_server_uses_other_timezone")


def _labels() -> dict[str, str]:
    # M2e records observations but intentionally does not classify any candidate as verified.
    return {candidate: "uninformative" for candidate in CANDIDATES}


def run_mt5_clock_check(symbol: str, *, mt5_module: Any | None = None,
                        output_json: str | Path | None = None, terminal_path: str | None = None) -> dict:
    """Collect observations but deliberately never make a timezone decision."""
    if not symbol or not symbol.strip():
        raise ValueError("symbol must not be blank")
    mt5 = mt5_module or importlib.import_module("MetaTrader5")
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "schema_version": 1, "symbol": symbol, "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "overall": "inconclusive", "decision": None, "timestamp_verification_status": "unverified",
        "evidence": [], "limitations": [
            "The PC clock is itself unverified.",
            "The D1 observation relies on the unverified assumption that a broker's daily boundary is server midnight.",
            "Tick-time comparison is meaningful only while the market is open and receiving ticks.",
            "These observations cannot conclusively establish broker timezone or bar-boundary semantics.",
        ], "api_calls": [],
    }
    initialized = False
    try:
        report["api_calls"].append("initialize")
        initialized = bool(mt5.initialize(**({"path": terminal_path} if terminal_path else {})))
        if not initialized:
            report["api_calls"].append("last_error")
            report["error"] = {"stage": "initialize", "detail": str(mt5.last_error())}
        else:
            report["api_calls"].append("symbol_select")
            if not mt5.symbol_select(symbol, True):
                report["api_calls"].append("last_error")
                report["error"] = {"stage": "symbol_select", "detail": str(mt5.last_error())}
            else:
                report["api_calls"].append("symbol_info_tick")
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    report["evidence"].append({"name": "tick_vs_pc_utc", "labels": _labels(), "observation": None,
                                                "reason": "No tick available; market may be closed or feed unavailable."})
                else:
                    raw_tick_time = _rate_field(tick, "time")
                    tick_utc = datetime.fromtimestamp(int(raw_tick_time), tz=timezone.utc) if raw_tick_time is not None else None
                    diff = (now - tick_utc).total_seconds() if tick_utc else None
                    report["evidence"].append({"name": "tick_vs_pc_utc", "labels": _labels(),
                                                "observation": {"tick_epoch_seconds": raw_tick_time,
                                                                "tick_interpreted_as_utc": tick_utc.isoformat().replace("+00:00", "Z") if tick_utc else None,
                                                                "pc_utc_at_check": now.isoformat().replace("+00:00", "Z"),
                                                                "pc_minus_tick_seconds": diff},
                                                "reason": "A tick timestamp comparison alone cannot verify the PC clock or broker timezone."})
                for timeframe in ("M1", "H4", "D1"):
                    report["api_calls"].append("copy_rates_from_pos")
                    rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, MT5_TIMEFRAMES[timeframe]), 0, 3)
                    opens = []
                    if rates is not None:
                        for rate in list(rates):
                            raw = _rate_field(rate, "time")
                            if raw is not None:
                                opens.append(datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat().replace("+00:00", "Z"))
                    report["evidence"].append({"name": f"{timeframe.lower()}_bar_open_observations", "labels": _labels(),
                                                "observation": {"returned_count": len(opens), "open_times_interpreted_as_utc": opens},
                                                "reason": "Raw epoch-derived observations only; no timezone or session-boundary verdict is inferred."})
    except Exception as exc:
        report["error"] = {"stage": "diagnostic", "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        if initialized:
            try:
                report["api_calls"].append("shutdown")
                mt5.shutdown()
            except Exception as exc:
                report["shutdown_error"] = f"{type(exc).__name__}: {exc}"
    # Enforced invariant: no diagnostic path can certify timestamp semantics.
    report["decision"] = None
    report["timestamp_verification_status"] = "unverified"
    report["overall"] = "inconclusive"
    if output_json is not None:
        path = Path(output_json).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
