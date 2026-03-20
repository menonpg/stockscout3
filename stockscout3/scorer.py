"""
scorer.py — VST + RS + RT momentum scorer for StockScout 3

Scores S&P 100 (or any ticker list) on three signals:
  VST  — Volume Surge Trend:  (avg_vol_5d / avg_vol_20d)
  RS   — Relative Strength:   stock 20d return vs SPY 20d return
  RT   — Recent Trend:        5d return

Gap filter baked in: if open[today] > close[yesterday] * 1.005, skip (limit-order framing).
Returns sorted DataFrame with columns: ticker, vst, rs, rt, score, gap_pct, skip_reason
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json, os, datetime

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

GAP_THRESHOLD = 0.005  # 0.5%


def score_universe(tickers=None, verbose=True) -> pd.DataFrame:
    if tickers is None:
        tickers = SP100

    spy = yf.download("SPY", period="30d", auto_adjust=True, progress=False)
    spy_close = spy["Close"].squeeze()
    spy_ret = float((spy_close.iloc[-1] / spy_close.iloc[-22]) - 1) if len(spy_close) >= 22 else 0.0

    rows = []
    for tkr in tickers:
        try:
            df = yf.download(tkr, period="30d", auto_adjust=True, progress=False)
            if df is None or len(df) < 22:
                continue

            close = df["Close"].squeeze()
            vol   = df["Volume"].squeeze()
            open_ = df["Open"].squeeze()

            vst = float(vol.iloc[-5:].mean() / vol.iloc[-20:].mean()) if vol.iloc[-20:].mean() > 0 else 1.0
            rs  = float((close.iloc[-1] / close.iloc[-22]) - 1) - spy_ret
            rt  = float((close.iloc[-1] / close.iloc[-6]) - 1)

            # gap filter
            gap_pct = float((open_.iloc[-1] / close.iloc[-2]) - 1) if len(close) >= 2 else 0.0
            skip = gap_pct > GAP_THRESHOLD

            score = (vst * 0.5) + (rs * 2.0) + (rt * 1.5)

            rows.append({
                "ticker": tkr, "vst": round(vst, 3), "rs": round(rs, 4),
                "rt": round(rt, 4), "score": round(score, 4),
                "gap_pct": round(gap_pct, 4), "gapped": skip,
            })
            if verbose:
                tag = " [GAP SKIP]" if skip else ""
                print(f"   {tkr}: vst={vst:.2f} rs={rs:.3f} rt={rt:.3f} score={score:.3f}{tag}")
        except Exception as e:
            if verbose:
                print(f"   {tkr}: error — {e}")

    df_out = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return df_out


def top_picks(df: pd.DataFrame, n=5) -> pd.DataFrame:
    """Return top N picks excluding gapped-up stocks."""
    return df[~df["gapped"]].head(n)


if __name__ == "__main__":
    print("Scoring S&P 100...")
    df = score_universe(verbose=True)
    picks = top_picks(df)
    print("\nTop 5 picks (gap-filtered):")
    print(picks[["ticker","vst","rs","rt","score","gap_pct"]].to_string(index=False))
    os.makedirs("data", exist_ok=True)
    df.to_json("data/scores_latest.json", orient="records", indent=2)
    print("\nSaved: data/scores_latest.json")
