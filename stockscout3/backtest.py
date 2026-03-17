"""
backtest.py — StockScout 3 backtester

Simulates the full pipeline:
  1. Score universe each day (VST+RS+RT)
  2. Apply gap filter (skip if open > prior_close * 1.005)
  3. Apply regime gate (trump-code predictions_log.json)
  4. Size positions (full/half/zero by regime)
  5. Track P&L vs SPY

Usage:
  python -m stockscout3.backtest --start 2024-01-01 --end 2025-12-31

Requires: data/ohlc_*.json (pre-fetched via fetch_history.py from stockscout-backtest)
"""

import json, os, sys, argparse, datetime
import pandas as pd
import numpy as np

DATA_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
TRUMP_LOG    = os.path.join(DATA_DIR, "trump_predictions.json")
GAP_THRESH   = 0.005
TRADE_SIZE   = 1000.0
N_PICKS      = 5


# ── helpers ──────────────────────────────────────────────────────────────────

def load_ohlc(ticker) -> pd.DataFrame | None:
    path = os.path.join(DATA_DIR, f"ohlc_{ticker}.json")
    if not os.path.exists(path):
        return None
    df = pd.read_json(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date").sort_index()


def load_trump_log() -> dict:
    """Returns {date_str: multiplier} from trump predictions_log.json"""
    if not os.path.exists(TRUMP_LOG):
        return {}
    log = json.load(open(TRUMP_LOG))
    result = {}
    for rec in log:
        d = str(rec.get("date", ""))[:10]
        direction   = str(rec.get("direction", "")).upper()
        confidence  = float(rec.get("confidence", 0.5))
        if direction == "UP"   and confidence >= 0.6:
            result[d] = 1.0
        elif direction == "DOWN" and confidence >= 0.6:
            result[d] = 0.0
        else:
            result[d] = 0.5
    return result


def score_day(tickers, ohlc: dict, date: datetime.date, prev_date: datetime.date) -> pd.DataFrame:
    rows = []
    spy_df = ohlc.get("SPY")
    if spy_df is None or prev_date not in spy_df.index or date not in spy_df.index:
        return pd.DataFrame()

    spy_dates = spy_df.index.tolist()
    spy_idx   = spy_dates.index(date)
    if spy_idx < 22:
        return pd.DataFrame()
    spy_ret = float(spy_df["close"].iloc[spy_idx] / spy_df["close"].iloc[spy_idx - 22] - 1)

    for tkr in tickers:
        df = ohlc.get(tkr)
        if df is None or date not in df.index or prev_date not in df.index:
            continue
        dates = df.index.tolist()
        idx   = dates.index(date)
        if idx < 22:
            continue

        close = df["close"]
        vol   = df["volume"]
        open_ = df["open"]

        vst = float(vol.iloc[idx-4:idx+1].mean() / vol.iloc[idx-19:idx+1].mean()) if vol.iloc[idx-19:idx+1].mean() > 0 else 1.0
        rs  = float(close.iloc[idx] / close.iloc[idx-22] - 1) - spy_ret
        rt  = float(close.iloc[idx] / close.iloc[idx-5]  - 1)

        gap_pct = float(open_.iloc[idx] / close.iloc[idx-1] - 1)
        gapped  = gap_pct > GAP_THRESH

        score = vst * 0.5 + rs * 2.0 + rt * 1.5
        rows.append({"ticker": tkr, "score": score, "gapped": gapped,
                     "open": float(open_.iloc[idx]), "close": float(close.iloc[idx])})

    return pd.DataFrame(rows).sort_values("score", ascending=False)


# ── main backtest ─────────────────────────────────────────────────────────────

def run(start: str, end: str, use_regime=True, verbose=False):
    from stockscout3.scorer import SP100

    tickers = SP100 + ["SPY"]
    print(f"Loading OHLC data for {len(tickers)} tickers...")
    ohlc = {t: load_ohlc(t) for t in tickers}
    ohlc = {k: v for k, v in ohlc.items() if v is not None}
    print(f"  Loaded {len(ohlc)} tickers")

    trump_log  = load_trump_log() if use_regime else {}
    spy_df     = ohlc.get("SPY")
    if spy_df is None:
        print("SPY data missing — aborting"); return

    trading_days = [d for d in spy_df.index
                    if str(start) <= str(d) <= str(end)
                    and d.weekday() < 5]

    portfolio_val = 0.0
    spy_start     = float(spy_df.loc[trading_days[0], "close"]) if trading_days else 1.0
    daily_returns = []
    trade_log     = []

    for i, date in enumerate(trading_days[1:], 1):
        prev = trading_days[i - 1]
        regime_mult = trump_log.get(str(date), 0.5) if use_regime else 1.0

        if regime_mult == 0.0:
            daily_returns.append({"date": str(date), "pnl": 0.0, "regime": "BEARISH", "trades": 0})
            continue

        df_scores = score_day(list(ohlc.keys()), ohlc, date, prev)
        if df_scores.empty:
            continue

        picks = df_scores[~df_scores["gapped"]].head(N_PICKS)
        if picks.empty:
            continue

        size = TRADE_SIZE * regime_mult
        day_pnl = 0.0
        for _, row in picks.iterrows():
            shares = int(size // row["open"])
            if shares < 1: continue
            pnl = (row["close"] - row["open"]) * shares
            day_pnl += pnl
            trade_log.append({"date": str(date), "ticker": row["ticker"],
                               "shares": shares, "entry": row["open"],
                               "exit": row["close"], "pnl": round(pnl, 2)})

        portfolio_val += day_pnl
        daily_returns.append({
            "date": str(date), "pnl": round(day_pnl, 2),
            "regime": "BULLISH" if regime_mult == 1.0 else "NEUTRAL",
            "trades": len(picks),
        })
        if verbose:
            print(f"  {date}  pnl=${day_pnl:+.2f}  trades={len(picks)}  regime={'B' if regime_mult==1.0 else 'N'}")

    # SPY benchmark
    spy_end = float(spy_df.loc[trading_days[-1], "close"]) if trading_days else spy_start
    spy_ret = (spy_end / spy_start - 1) * 100

    # Stats
    pnls = [d["pnl"] for d in daily_returns]
    total_invested = TRADE_SIZE * N_PICKS * len([p for p in pnls if p != 0])
    total_return_pct = (portfolio_val / total_invested * 100) if total_invested > 0 else 0
    sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0
    cum = np.cumsum(pnls)
    drawdown = float(np.min(cum - np.maximum.accumulate(cum)))

    results = {
        "start": start, "end": end, "use_regime": use_regime,
        "total_pnl": round(portfolio_val, 2),
        "total_return_pct": round(total_return_pct, 2),
        "spy_return_pct": round(spy_ret, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(drawdown, 2),
        "total_trades": len(trade_log),
        "trading_days": len(daily_returns),
        "daily_returns": daily_returns,
        "trade_log": trade_log,
    }
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end",   default=str(datetime.date.today()))
    ap.add_argument("--no-regime", action="store_true")
    ap.add_argument("--verbose",   action="store_true")
    args = ap.parse_args()

    results = run(args.start, args.end, use_regime=not args.no_regime, verbose=args.verbose)
    if results:
        print(f"\n{'='*50}")
        print(f"StockScout 3 Backtest Results")
        print(f"{'='*50}")
        print(f"Period:        {results['start']} to {results['end']}")
        print(f"Regime gate:   {'ON' if results['use_regime'] else 'OFF'}")
        print(f"Total P&L:     ${results['total_pnl']:+,.2f}")
        print(f"Return:        {results['total_return_pct']:+.2f}%")
        print(f"SPY:           {results['spy_return_pct']:+.2f}%")
        print(f"Sharpe:        {results['sharpe']:.3f}")
        print(f"Max Drawdown:  ${results['max_drawdown']:,.2f}")
        print(f"Total Trades:  {results['total_trades']}")
        os.makedirs(DATA_DIR, exist_ok=True)
        out = os.path.join(DATA_DIR, "backtest_results.json")
        json.dump(results, open(out, "w"), indent=2, default=str)
        print(f"\nSaved: {out}")
