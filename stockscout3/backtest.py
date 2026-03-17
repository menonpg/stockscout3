#!/usr/bin/env python3
"""
simulate.py — Walk through scored history, pick top N each day,
measure next-day open → close return, compute hit rate + P&L.

Outputs: backtest/data/results.json
"""

import json, os, sys
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "..", "data")
HIST_FILE  = os.path.join(DATA_DIR, "scored_history.json")
OUT_FILE   = os.path.join(DATA_DIR, "results.json")

TOP_N        = 5      # picks per day
POSITION_SZ  = 10000  # dollars per position — $10K × 5 = $50K total capital deployed per day

# Ranking modes:
#   "equal"  — sort by vst (rv+rs+rt)/3  [original]
#   "safety" — sort by RS*0.5 + RT*0.3 + VST*0.2  [production portfolio.py logic]
import argparse
_parser = argparse.ArgumentParser()
_parser.add_argument("--mode",        default="safety",  choices=["equal","safety","intraday"])
_parser.add_argument("--min-vst",     type=float, default=1.0,   help="Min VST threshold (try 1.0/1.5/2.0/2.5)")
_parser.add_argument("--max-beta",    type=float, default=99.0,  help="Max beta filter (try 1.3, 1.5)")
_parser.add_argument("--max-gap-pct", type=float, default=99.0,  help="Skip if open gap > X%% vs prior close (try 0.5, 1.0)")
_parser.add_argument("--vix-max",     type=float, default=99.0,  help="Skip trading days when VIX > X (try 25, 30)")
_parser.add_argument("--out-suffix",  type=str,   default="",    help="Suffix appended to results filename, e.g. _vst15")
_args, _ = _parser.parse_known_args()
RANK_MODE    = _args.mode
MIN_VST      = _args.min_vst
MAX_BETA     = _args.max_beta
MAX_GAP_PCT  = _args.max_gap_pct
VIX_MAX      = _args.vix_max
OUT_SUFFIX   = _args.out_suffix

def rank_score(c):
    if RANK_MODE == "safety":
        # Production logic: RS-heavy (good for multi-day, bad intraday)
        return c["rs"] * 0.5 + c["rt"] * 0.3 + c["vst"] * 0.2
    elif RANK_MODE == "intraday":
        # RT-dominant: favor recent trajectory over relative strength
        # RS inverted slightly — avoid names already extended vs market
        return c["rt"] * 0.6 + c["vst"] * 0.3 - c["rs"] * 0.1
    return c["vst"]  # equal: sort by vst only

# ── Trump regime gate ────────────────────────────────────────────────────────
import collections as _col

def _load_trump_regime():
    import os as _os
    trump_path = _os.path.join(DATA_DIR, "trump_predictions.json")
    if not _os.path.exists(trump_path):
        return {}
    log = json.load(open(trump_path))
    DIR_MAP = {"LONG":1.0,"UP":1.0,"SHORT":0.0,"DOWN":0.0,"VOLATILE":0.5,"NEUTRAL":0.5}
    by_date = _col.defaultdict(list)
    for rec in log:
        d = str(rec.get("date_signal",""))[:10]
        if d:
            by_date[d].append(DIR_MAP.get(str(rec.get("direction","")).upper(), 0.5))
    result = {}
    for d, votes in by_date.items():
        vc = _col.Counter(votes)
        result[d] = 0.0 if (vc[0.0] > 0 and vc[1.0] == 0) else vc.most_common(1)[0][0]
    return result

_parser.add_argument("--regime", action="store_true", help="Enable Trump Code regime gate")
_args, _ = _parser.parse_known_args()
USE_REGIME = _args.regime
TRUMP_REGIME = _load_trump_regime() if USE_REGIME else {}
if USE_REGIME:
    print(f"Trump regime gate: ON ({len(TRUMP_REGIME)} days loaded)")

if not os.path.exists(HIST_FILE):
    print("ERROR: scored_history.json not found. Run score_history.py first.")
    sys.exit(1)

history = json.load(open(HIST_FILE))
trading_dates = sorted(history.keys())

print(f"Loaded {len(trading_dates)} scored trading days")
print(f"Simulating top-{TOP_N} picks, min VST={MIN_VST}, max_beta={MAX_BETA}, "
      f"max_gap={MAX_GAP_PCT}%, vix_max={VIX_MAX}, ${POSITION_SZ}/position\n")

# Build OHLC lookup for next-day open/close
ticker_ohlc = {}
for fname in os.listdir(DATA_DIR):
    if fname.startswith("ohlc_") and fname.endswith(".json"):
        ticker = fname[5:-5]
        try:
            d = json.load(open(os.path.join(DATA_DIR, fname)))
            ticker_ohlc[ticker] = d.get("data", {})
        except:
            pass

# Build beta lookup from fund files
ticker_beta = {}
for fname in os.listdir(DATA_DIR):
    if fname.startswith("fund_") and fname.endswith(".json"):
        ticker = fname[5:-5]
        try:
            d = json.load(open(os.path.join(DATA_DIR, fname)))
            b = d.get("Beta", "")
            ticker_beta[ticker] = float(b) if b else 1.0
        except:
            ticker_beta[ticker] = 1.0

# VIX by date (from ohlc_VIX.json if fetched, else skip filter)
vix_by_date = {}
vix_path = os.path.join(DATA_DIR, "ohlc_VIX.json")  # or ohlc_^VIX.json
if not os.path.exists(vix_path):
    vix_path = os.path.join(DATA_DIR, "ohlc_^VIX.json")
if os.path.exists(vix_path):
    try:
        vd = json.load(open(vix_path)).get("data", {})
        for dt, row in vd.items():
            c = row.get("4. close") or row.get("5. adjusted close")
            if c: vix_by_date[dt] = float(c)
    except:
        pass

def get_open(ticker, date_str):
    ohlc = ticker_ohlc.get(ticker, {})
    row  = ohlc.get(date_str, {})
    try:
        return float(row.get("1. open") or 0)
    except:
        return 0

def get_close(ticker, date_str):
    ohlc = ticker_ohlc.get(ticker, {})
    row  = ohlc.get(date_str, {})
    try:
        return float(row.get("4. close") or row.get("5. adjusted close") or 0)
    except:
        return 0

# ── Simulation ────────────────────────────────────────────────────────────────

daily_results   = []
cumulative_pnl  = 0.0
total_trades    = 0
wins            = 0
losses          = 0
no_data_days    = 0

for i, day in enumerate(trading_dates[:-1]):  # need a "next day"
    next_day   = trading_dates[i + 1]
    candidates = history[day]

    # Trump regime gate
    if USE_REGIME:
        regime_mult = TRUMP_REGIME.get(day, 0.5)
        if regime_mult == 0.0:
            daily_results.append({"date": day, "picks": [], "day_pnl": 0,
                "cumulative_pnl": round(cumulative_pnl, 2), "note": "BEARISH regime"})
            continue

    # VIX day-level filter
    if VIX_MAX < 99 and vix_by_date:
        day_vix = vix_by_date.get(day)
        if day_vix and day_vix > VIX_MAX:
            daily_results.append({"date": day, "picks": [], "day_pnl": 0,
                "cumulative_pnl": round(cumulative_pnl, 2), "note": f"skipped: VIX={day_vix:.1f}>{VIX_MAX}"})
            continue

    # Filter: VST threshold, beta cap, opening gap
    eligible = []
    for c in candidates:
        if c["vst"] < MIN_VST:
            continue
        # Beta filter
        beta = ticker_beta.get(c["ticker"], 1.0)
        if beta > MAX_BETA:
            continue
        # Gap filter — compare next-day open vs current close
        if MAX_GAP_PCT < 99:
            cur_close  = get_close(c["ticker"], day)
            next_open  = get_open(c["ticker"], next_day)
            if cur_close > 0 and next_open > 0:
                gap_pct = (next_open - cur_close) / cur_close * 100
                if gap_pct > MAX_GAP_PCT:
                    continue  # skip stocks that already gapped up too much
        eligible.append(c)

    eligible.sort(key=rank_score, reverse=True)
    picks = eligible[:TOP_N]

    if not picks:
        daily_results.append({
            "date": day,
            "picks": [],
            "day_pnl": 0,
            "cumulative_pnl": round(cumulative_pnl, 2),
            "note": "no picks above threshold"
        })
        continue

    day_pnl   = 0
    day_trades = []

    for pick in picks:
        t      = pick["ticker"]
        open_  = get_open(t, next_day)
        close_ = get_close(t, next_day)

        if open_ == 0 or close_ == 0:
            no_data_days += 1
            continue

        ret_pct = (close_ - open_) / open_ * 100
        pnl     = POSITION_SZ * (ret_pct / 100)
        won     = ret_pct > 0

        day_pnl    += pnl
        total_trades += 1
        if won: wins += 1
        else:   losses += 1

        day_trades.append({
            "ticker":   t,
            "vst":      pick["vst"],
            "rv":       pick["rv"],
            "rs":       pick["rs"],
            "rt":       pick["rt"],
            "open":     round(open_, 2),
            "close":    round(close_, 2),
            "ret_pct":  round(ret_pct, 3),
            "pnl":      round(pnl, 2),
            "won":      won
        })

    cumulative_pnl += day_pnl
    daily_results.append({
        "date":            day,
        "next_day":        next_day,
        "picks":           day_trades,
        "day_pnl":         round(day_pnl, 2),
        "cumulative_pnl":  round(cumulative_pnl, 2),
    })

# ── Summary stats ─────────────────────────────────────────────────────────────

hit_rate = (wins / total_trades * 100) if total_trades > 0 else 0

# Sharpe (daily returns, annualized)
day_pnls = [d["day_pnl"] for d in daily_results if d["picks"]]
if len(day_pnls) > 1:
    import statistics
    mean_pnl   = statistics.mean(day_pnls)
    std_pnl    = statistics.stdev(day_pnls)
    sharpe     = (mean_pnl / std_pnl * (252 ** 0.5)) if std_pnl > 0 else 0
else:
    sharpe = 0

# Max drawdown
peak = 0
max_dd = 0
running = 0
for d in daily_results:
    running += d["day_pnl"]
    if running > peak:
        peak = running
    dd = peak - running
    if dd > max_dd:
        max_dd = dd

# Best/worst days
sorted_days = sorted([d for d in daily_results if d["picks"]], key=lambda x: x["day_pnl"])
worst_days  = sorted_days[:5]
best_days   = sorted_days[-5:][::-1]

# Win streaks
streak = 0
max_streak = 0
lose_streak = 0
max_lose_streak = 0
for d in daily_results:
    if d.get("picks"):
        if d["day_pnl"] > 0:
            streak += 1
            lose_streak = 0
            max_streak = max(max_streak, streak)
        else:
            lose_streak += 1
            streak = 0
            max_lose_streak = max(max_lose_streak, lose_streak)

summary = {
    "generated_at":      datetime.now().isoformat(),
    "rank_mode":         RANK_MODE,
    "backtest_start":    trading_dates[0],
    "backtest_end":      trading_dates[-1],
    "total_trading_days": len(trading_dates),
    "days_with_picks":   len([d for d in daily_results if d["picks"]]),
    "top_n":             TOP_N,
    "min_vst":           MIN_VST,
    "position_size":     POSITION_SZ,
    "total_trades":      total_trades,
    "wins":              wins,
    "losses":            losses,
    "hit_rate_pct":      round(hit_rate, 1),
    "total_pnl":         round(cumulative_pnl, 2),
    "total_capital":     TOP_N * POSITION_SZ,
    "position_size":     POSITION_SZ,
    "total_pnl_pct":     round(cumulative_pnl / (TOP_N * POSITION_SZ) * 100, 2),
    "sharpe_annualized": round(sharpe, 3),
    "max_drawdown":      round(max_dd, 2),
    "max_win_streak":    max_streak,
    "max_lose_streak":   max_lose_streak,
    "no_data_skipped":   no_data_days,
    "bearish_days_skipped": len([d for d in daily_results if d.get("note") == "BEARISH regime"]),
}

output = {
    "summary":       summary,
    "daily":         daily_results,
    "best_days":     best_days,
    "worst_days":    worst_days,
}

key = f"{RANK_MODE}{OUT_SUFFIX}"
mode_file = os.path.join(DATA_DIR, f"results_{key}.json")
json.dump(output, open(mode_file, "w"), indent=2)
# results.json = safety mode (default dashboard)
if RANK_MODE == "safety" and not OUT_SUFFIX:
    json.dump(output, open(OUT_FILE, "w"), indent=2)

print("=" * 55)
print(f"  Backtest: {summary['backtest_start']} → {summary['backtest_end']}")
print(f"  Trading days:  {summary['total_trading_days']}")
print(f"  Total trades:  {total_trades}  (W:{wins} / L:{losses})")
print(f"  Hit rate:      {hit_rate:.1f}%")
print(f"  Total P&L:     ${cumulative_pnl:,.2f}  ({summary['total_pnl_pct']}%)")
print(f"  Sharpe:        {sharpe:.3f}")
print(f"  Max drawdown:  ${max_dd:,.2f}")
print(f"  Win streak:    {max_streak}  |  Lose streak: {max_lose_streak}")
print("=" * 55)
print(f"\nSaved to {OUT_FILE}")
