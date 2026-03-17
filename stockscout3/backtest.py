"""
backtest.py — StockScout 3 backtester
Simulates VST+RS+RT + gap filter + optional Trump regime gate.
"""

import json, os, sys, argparse, datetime
import pandas as pd
import numpy as np

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
TRUMP_LOG   = os.path.join(DATA_DIR, "trump_predictions.json")
GAP_THRESH  = 0.005
TRADE_SIZE  = 1000.0
N_PICKS     = 5

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


def load_ohlc(ticker):
    fpath = os.path.join(DATA_DIR, f"ohlc_{ticker}.json")
    if not os.path.exists(fpath):
        return None
    raw = json.load(open(fpath))
    # Handle AV format: {"data": {"YYYY-MM-DD": {"1. open":..., "4. close":..., "6. volume":...}}}
    if isinstance(raw, dict) and "data" in raw:
        inner = raw["data"]
        rows = []
        for d, v in inner.items():
            try:
                rows.append({
                    "date": datetime.date.fromisoformat(d),
                    "open":   float(v.get("1. open",  v.get("open",  0))),
                    "close":  float(v.get("4. close", v.get("close", 0))),
                    "volume": float(v.get("6. volume",v.get("volume",0))),
                })
            except Exception:
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows).set_index("date").sort_index()
        return df
    # Handle flat list format: [{"date":..., "open":..., "close":..., "volume":...}]
    try:
        df = pd.read_json(fpath)
        if "date" not in df.columns:
            return None
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df.set_index("date").sort_index()
    except Exception:
        return None


def load_trump_regime() -> dict:
    """Returns {date_str: multiplier} from local trump_predictions.json"""
    if not os.path.exists(TRUMP_LOG):
        return {}
    import collections
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
        if vc[0.0] > 0 and vc[1.0] == 0:
            result[d] = 0.0
        else:
            result[d] = vc.most_common(1)[0][0]
    return result


def score_day(ohlc, tickers, date, spy_ret):
    rows = []
    for tkr in tickers:
        df = ohlc.get(tkr)
        if df is None or date not in df.index:
            continue
        dates = df.index.tolist()
        idx = dates.index(date)
        if idx < 22:
            continue
        close = df["close"] if "close" in df.columns else df["Close"]
        vol   = df["volume"] if "volume" in df.columns else df["Volume"]
        open_ = df["open"]   if "open"  in df.columns else df["Open"]

        vst = float(vol.iloc[idx-4:idx+1].mean() / vol.iloc[idx-19:idx+1].mean()) if vol.iloc[idx-19:idx+1].mean() > 0 else 1.0
        rs  = float(close.iloc[idx] / close.iloc[idx-22] - 1) - spy_ret
        rt  = float(close.iloc[idx] / close.iloc[idx-5]  - 1)
        gap = float(open_.iloc[idx] / close.iloc[idx-1]  - 1)

        score = vst * 0.5 + rs * 2.0 + rt * 1.5
        rows.append({"ticker": tkr, "score": score, "gapped": gap > GAP_THRESH,
                     "open": float(open_.iloc[idx]), "close": float(close.iloc[idx])})
    return pd.DataFrame(rows).sort_values("score", ascending=False) if rows else pd.DataFrame()


def run(start, end, use_regime=True, verbose=False):
    print(f"Loading OHLC...")
    tickers = SP100 + ["SPY"]
    ohlc = {t: load_ohlc(t) for t in tickers}
    ohlc = {k: v for k, v in ohlc.items() if v is not None}
    print(f"  {len(ohlc)} tickers loaded")

    trump = load_trump_regime() if use_regime else {}
    if use_regime:
        print(f"  Trump regime: {len(trump)} days loaded")

    spy_df = ohlc.get("SPY")
    if spy_df is None:
        print("SPY missing"); return None

    close_col = "close" if "close" in spy_df.columns else "Close"
    trading_days = [d for d in spy_df.index
                    if str(start) <= str(d) <= str(end) and d.weekday() < 5]
    if len(trading_days) < 25:
        print("Not enough trading days"); return None

    spy_start = float(spy_df[close_col].iloc[spy_df.index.tolist().index(trading_days[0])])
    portfolio_val = 0.0
    daily = []
    trades = []
    skipped_bearish = 0

    for i, date in enumerate(trading_days[1:], 1):
        prev = trading_days[i-1]
        spy_dates = spy_df.index.tolist()
        spy_idx = spy_dates.index(date)
        spy_ret = float(spy_df[close_col].iloc[spy_idx] / spy_df[close_col].iloc[spy_idx-22] - 1) if spy_idx >= 22 else 0.0

        regime = trump.get(str(date), 0.5) if use_regime else 1.0
        if regime == 0.0:
            skipped_bearish += 1
            daily.append({"date": str(date), "pnl": 0.0, "regime": "BEARISH", "n": 0})
            continue

        df_s = score_day(ohlc, list(ohlc.keys()), date, spy_ret)
        if df_s.empty:
            continue

        picks = df_s[~df_s["gapped"]].head(N_PICKS)
        size = TRADE_SIZE * regime
        day_pnl = 0.0
        for _, row in picks.iterrows():
            sh = int(size // row["open"])
            if sh < 1: continue
            pnl = (row["close"] - row["open"]) * sh
            day_pnl += pnl
            trades.append({"date": str(date), "ticker": row["ticker"],
                           "shares": sh, "entry": row["open"],
                           "exit": row["close"], "pnl": round(pnl,2)})
        portfolio_val += day_pnl
        daily.append({"date": str(date), "pnl": round(day_pnl,2),
                      "regime": "BULLISH" if regime==1.0 else "NEUTRAL", "n": len(picks)})
        if verbose:
            print(f"  {date} pnl=${day_pnl:+.2f} regime={'B' if regime==1.0 else 'N'} picks={len(picks)}")

    spy_end = float(spy_df[close_col].iloc[spy_df.index.tolist().index(trading_days[-1])])
    spy_ret_total = (spy_end / spy_start - 1) * 100

    pnls = np.array([d["pnl"] for d in daily])
    invested = TRADE_SIZE * N_PICKS * max(len([p for p in pnls if p != 0]), 1)
    ret_pct = portfolio_val / invested * 100
    sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0
    cum = np.cumsum(pnls)
    dd = float(np.min(cum - np.maximum.accumulate(cum)))
    wins = sum(1 for t in trades if t["pnl"] > 0)
    hit_rate = wins / len(trades) * 100 if trades else 0

    return {
        "start": start, "end": end, "use_regime": use_regime,
        "total_pnl": round(portfolio_val, 2),
        "return_pct": round(ret_pct, 2),
        "spy_pct": round(spy_ret_total, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_dollars": round(dd, 2),
        "total_trades": len(trades),
        "hit_rate_pct": round(hit_rate, 1),
        "bearish_days_skipped": skipped_bearish,
        "trading_days": len(daily),
        "daily": daily,
        "trades": trades,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end",   default=str(datetime.date.today()))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print(f"\n{'='*55}")
    print(f"  StockScout 3 Backtest — {args.start} to {args.end}")
    print(f"{'='*55}")

    for regime_on in [False, True]:
        label = "WITH regime gate" if regime_on else "WITHOUT regime gate"
        print(f"\n--- {label} ---")
        r = run(args.start, args.end, use_regime=regime_on, verbose=args.verbose)
        if r:
            print(f"  Return:          {r['return_pct']:+.2f}%")
            print(f"  SPY:             {r['spy_pct']:+.2f}%")
            print(f"  Sharpe:          {r['sharpe']:.3f}")
            print(f"  Max DD ($):      ${r['max_drawdown_dollars']:,.2f}")
            print(f"  Trades:          {r['total_trades']}")
            print(f"  Hit rate:        {r['hit_rate_pct']:.1f}%")
            if regime_on:
                print(f"  Bearish skipped: {r['bearish_days_skipped']} days")
            tag = "regime" if regime_on else "baseline"
            out = os.path.join(DATA_DIR, f"backtest_{tag}.json")
            json.dump(r, open(out,"w"), indent=2, default=str)
            print(f"  Saved: {out}")
