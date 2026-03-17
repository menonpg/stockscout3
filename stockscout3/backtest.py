#!/usr/bin/env python3
"""
backtest.py — StockScout 3 backtester
Mirrors simulate.py logic exactly:
  - Signal day D: score universe
  - Execution day D+1: buy at open, sell at close
  - Gap filter: skip if D+1 open > D close * (1 + gap_thresh)
  - Regime gate: skip entire day if Trump Code says BEARISH

OHLC format expected: {"data": {"YYYY-MM-DD": {"1. open":..., "4. close":..., "6. volume":...}}}
"""

import json, os, sys, argparse, datetime, statistics
from pathlib import Path

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
TRUMP_LOG  = os.path.join(DATA_DIR, "trump_predictions.json")

TOP_N        = 5
POSITION_SZ  = 10000   # $10K per position = $50K total capital (matches simulate.py)
GAP_THRESH   = 0.005   # 0.5% gap filter

SP100 = [
    "AAPL","ABBV","ABT","ACN","ADBE","ADI","ADP","AMGN","AMT","AMZN",
    "AVGO","AXP","BAC","BK","BKNG","BLK","BMY","BRK-B","C","CAT",
    "CB","CHTR","CL","CMCSA","COF","COP","CRM","CSCO","CVS","CVX",
    "DE","DHR","DIS","DUK","EMR","EXC","F","FDX","GD","GE","GILD",
    "GM","GOOG","GOOGL","GS","HD","HON","HUM","IBM","INTC","INTU",
    "JNJ","JPM","KHC","KO","LIN","LLY","LMT","LOW","MA","MCD","MCO",
    "MDT","MET","META","MMC","MMM","MO","MRK","MS","MSFT","NEE","NFLX",
    "NKE","NOW","NSC","NVDA","ORCL","PEP","PFE","PG","PM","PYPL",
    "QCOM","RTX","SBUX","SCHW","SO","SPG","T","TGT","TMO","TMUS",
    "TXN","UNH","UNP","UPS","USB","V","VZ","WFC","WMT","XOM",
]


def load_ohlc_all():
    """Load all ohlc_*.json files. Returns {ticker: {date_str: {open, close, volume}}}"""
    ohlc = {}
    data_path = Path(DATA_DIR)
    for f in data_path.glob("ohlc_*.json"):
        ticker = f.stem[5:]  # strip "ohlc_"
        try:
            raw = json.loads(f.read_text())
            inner = raw.get("data", {})
            ohlc[ticker] = {
                d: {
                    "open":   float(v.get("1. open",  0)),
                    "close":  float(v.get("4. close", v.get("5. adjusted close", 0))),
                    "volume": float(v.get("6. volume", 0)),
                }
                for d, v in inner.items()
            }
        except Exception as e:
            pass
    return ohlc


def load_trump_regime():
    """Returns {date_str: multiplier} 1.0=bullish 0.5=neutral 0.0=bearish"""
    import collections
    if not os.path.exists(TRUMP_LOG):
        return {}
    log = json.load(open(TRUMP_LOG))
    DIR_MAP = {"LONG":1.0,"UP":1.0,"SHORT":0.0,"DOWN":0.0,"VOLATILE":0.5,"NEUTRAL":0.5}
    by_date = collections.defaultdict(list)
    for rec in log:
        d = str(rec.get("date_signal",""))[:10]
        if d:
            by_date[d].append(DIR_MAP.get(str(rec.get("direction","")).upper(), 0.5))
    result = {}
    for d, votes in by_date.items():
        vc = collections.Counter(votes)
        result[d] = 0.0 if (vc[0.0] > 0 and vc[1.0] == 0) else vc.most_common(1)[0][0]
    return result


def score_ticker(ticker, ohlc_data, signal_date, trading_dates):
    """Score a ticker on signal_date using VST+RS+RT. Returns dict or None."""
    dates = sorted(ohlc_data.keys())
    if signal_date not in dates:
        return None
    idx = dates.index(signal_date)
    if idx < 22:
        return None

    # Build arrays
    closes  = [ohlc_data[d]["close"]  for d in dates]
    volumes = [ohlc_data[d]["volume"] for d in dates]

    c   = closes[idx]
    c22 = closes[idx - 22]
    c5  = closes[idx - 5]

    avg_vol5  = sum(volumes[idx-4:idx+1]) / 5
    avg_vol20 = sum(volumes[idx-19:idx+1]) / 20

    vst = avg_vol5 / avg_vol20 if avg_vol20 > 0 else 1.0
    rt  = (c - c5)  / c5  if c5  > 0 else 0.0
    # RS computed against SPY — passed in externally
    return {"vst": vst, "rt": rt, "close": c}


def run(start="2024-01-01", end=None, use_regime=True, verbose=False):
    if end is None:
        end = str(datetime.date.today())

    print(f"Loading OHLC data...")
    ohlc = load_ohlc_all()
    print(f"  {len(ohlc)} tickers loaded")

    spy_ohlc = ohlc.get("SPY", {})
    if not spy_ohlc:
        print("ERROR: SPY data missing"); return None

    trump = load_trump_regime() if use_regime else {}
    if use_regime:
        print(f"  Trump regime: {len(trump)} days loaded")

    # All trading dates from SPY, filtered to range
    trading_dates = sorted(d for d in spy_ohlc if start <= d <= end)
    print(f"  Trading days: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")

    # Precompute SPY 22d return for each date (for RS)
    spy_dates  = sorted(spy_ohlc.keys())
    spy_ret22  = {}
    for i, d in enumerate(spy_dates):
        if i >= 22:
            spy_ret22[d] = (spy_ohlc[d]["close"] / spy_ohlc[spy_dates[i-22]]["close"]) - 1

    daily_results  = []
    cumulative_pnl = 0.0
    total_trades   = 0
    wins = losses  = 0
    bearish_skipped = 0

    for i, signal_day in enumerate(trading_dates[:-1]):
        exec_day = trading_dates[i + 1]

        # Regime gate
        if use_regime:
            regime = trump.get(signal_day, 0.5)
            if regime == 0.0:
                bearish_skipped += 1
                daily_results.append({"date": signal_day, "picks": [], "day_pnl": 0,
                    "cumulative_pnl": round(cumulative_pnl, 2), "note": "BEARISH regime"})
                continue

        # Score all tickers on signal_day
        spy_20d = spy_ret22.get(signal_day, 0.0)
        scored = []
        for ticker in SP100:
            td = ohlc.get(ticker)
            if not td:
                continue
            s = score_ticker(ticker, td, signal_day, trading_dates)
            if not s:
                continue
            # RS = stock 22d return - SPY 22d return
            s22 = sorted(td.keys())
            try:
                idx22 = s22.index(signal_day)
                if idx22 < 22:
                    continue
                rs = (s["close"] / td[s22[idx22-22]]["close"] - 1) - spy_20d
            except (ValueError, ZeroDivisionError):
                continue
            score = s["vst"] * 0.5 + rs * 2.0 + s["rt"] * 1.5
            scored.append({"ticker": ticker, "vst": round(s["vst"],3),
                           "rs": round(rs,4), "rt": round(s["rt"],4),
                           "score": round(score,4), "close": s["close"]})

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Gap filter + pick top N
        picks = []
        for c in scored:
            if len(picks) >= TOP_N:
                break
            exec_data = ohlc.get(c["ticker"], {}).get(exec_day)
            if not exec_data:
                continue
            gap = (exec_data["open"] - c["close"]) / c["close"] if c["close"] > 0 else 0
            if gap > GAP_THRESH:
                continue  # gapped up too much
            picks.append({**c, "exec_open": exec_data["open"], "exec_close": exec_data["close"], "gap": gap})

        if not picks:
            daily_results.append({"date": signal_day, "picks": [], "day_pnl": 0,
                "cumulative_pnl": round(cumulative_pnl, 2), "note": "no picks"})
            continue

        # Execute: buy open, sell close on exec_day
        day_pnl = 0.0
        trade_log = []
        for p in picks:
            o, c2 = p["exec_open"], p["exec_close"]
            if o == 0 or c2 == 0:
                continue
            ret_pct = (c2 - o) / o
            pnl     = POSITION_SZ * ret_pct
            day_pnl += pnl
            total_trades += 1
            if pnl > 0: wins += 1
            else: losses += 1
            trade_log.append({
                "ticker": p["ticker"], "vst": p["vst"], "rs": p["rs"], "rt": p["rt"],
                "open": round(o,2), "close": round(c2,2),
                "ret_pct": round(ret_pct*100, 3), "pnl": round(pnl,2), "won": pnl>0
            })

        cumulative_pnl += day_pnl
        regime_label = "BULLISH" if trump.get(signal_day,0.5)==1.0 else "NEUTRAL"
        daily_results.append({
            "date": signal_day, "next_day": exec_day,
            "picks": trade_log, "day_pnl": round(day_pnl,2),
            "cumulative_pnl": round(cumulative_pnl,2),
            "regime": regime_label if use_regime else "—",
        })
        if verbose:
            print(f"  {signal_day}->{exec_day}  pnl=${day_pnl:+.2f}  picks={len(picks)}")

    # ── Stats ──────────────────────────────────────────────────────────────
    total_capital = TOP_N * POSITION_SZ  # $50K
    total_pnl_pct = cumulative_pnl / total_capital * 100

    day_pnls = [d["day_pnl"] for d in daily_results if d.get("picks")]
    if len(day_pnls) > 1:
        mean_p = statistics.mean(day_pnls)
        std_p  = statistics.stdev(day_pnls)
        sharpe = (mean_p / std_p * (252**0.5)) if std_p > 0 else 0
    else:
        sharpe = 0

    peak = max_dd = running = 0
    for d in daily_results:
        running += d["day_pnl"]
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    hit_rate = wins / total_trades * 100 if total_trades else 0

    # SPY return over same period
    spy_start = spy_ohlc.get(trading_dates[0], {}).get("close", 1)
    spy_end   = spy_ohlc.get(trading_dates[-1], {}).get("close", 1)
    spy_pct   = (spy_end / spy_start - 1) * 100

    # Best/worst days
    days_with_picks = [d for d in daily_results if d.get("picks")]
    best_days  = sorted(days_with_picks, key=lambda x: x["day_pnl"], reverse=True)[:5]
    worst_days = sorted(days_with_picks, key=lambda x: x["day_pnl"])[:5]

    # Flat trade list for trade book
    all_trades = [t for d in daily_results for t in d.get("picks",[])]
    for d in daily_results:
        for t in d.get("picks",[]):
            t["date"] = d["date"]

    summary = {
        "backtest_start": trading_dates[0], "backtest_end": trading_dates[-1],
        "use_regime": use_regime,
        "total_trading_days": len(trading_dates),
        "days_with_picks": len(days_with_picks),
        "top_n": TOP_N, "position_size": POSITION_SZ, "total_capital": total_capital,
        "total_trades": total_trades, "wins": wins, "losses": losses,
        "hit_rate_pct": round(hit_rate, 1),
        "total_pnl": round(cumulative_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "spy_pct": round(spy_pct, 2),
        "sharpe_annualized": round(sharpe, 3),
        "max_drawdown": round(max_dd, 2),
        "bearish_days_skipped": bearish_skipped,
    }

    return {
        "summary": summary,
        "daily": daily_results,
        "best_days": best_days,
        "worst_days": worst_days,
        "trades": [t for d in daily_results for t in d.get("picks",[])],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end",   default=str(datetime.date.today()))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print(f"\n{'='*55}")
    print(f"  StockScout 3 Backtest  {args.start} to {args.end}")
    print(f"  Capital: ${TOP_N * POSITION_SZ:,}  ({TOP_N} x ${POSITION_SZ:,})")
    print(f"{'='*55}")

    os.makedirs(DATA_DIR, exist_ok=True)

    for regime_on, label in [(False,"WITHOUT regime gate"), (True,"WITH regime gate")]:
        print(f"\n--- {label} ---")
        r = run(args.start, args.end, use_regime=regime_on, verbose=args.verbose)
        if not r:
            continue
        s = r["summary"]
        print(f"  Return:          {s['total_pnl_pct']:+.2f}%  (${s['total_pnl']:+,.2f})")
        print(f"  SPY:             {s['spy_pct']:+.2f}%")
        print(f"  Sharpe:          {s['sharpe_annualized']:.3f}")
        print(f"  Max Drawdown:    ${s['max_drawdown']:,.2f}")
        print(f"  Trades:          {s['total_trades']}  (W:{s['wins']} / L:{s['losses']})")
        print(f"  Hit Rate:        {s['hit_rate_pct']:.1f}%")
        if regime_on:
            print(f"  Bearish skipped: {s['bearish_days_skipped']} days")
        tag = "regime" if regime_on else "baseline"
        out = os.path.join(DATA_DIR, f"backtest_{tag}.json")
        json.dump(r, open(out,"w"), indent=2, default=str)
        print(f"  Saved: {out}")
