"""
portfolio.py — Open and close positions for StockScout 3

Usage:
  python -m stockscout3.portfolio open   # 9:30 AM — open positions
  python -m stockscout3.portfolio close  # 4:00 PM — close positions + log P&L

Position sizing is regime-scaled:
  BULLISH (1.0) -> full $1000/position
  NEUTRAL (0.5) -> $500/position
  BEARISH (0.0) -> skip entirely

Writes to data/trades/YYYY-MM-DD.json
"""

import yfinance as yf
import json, os, sys, datetime

TRADE_SIZE_FULL = 1000.0   # dollars per position at full regime
N_POSITIONS     = 5
TRADES_DIR      = os.path.join(os.path.dirname(__file__), "..", "data", "trades")


def _today():
    return str(datetime.date.today())


def _trade_path(date=None):
    os.makedirs(TRADES_DIR, exist_ok=True)
    return os.path.join(TRADES_DIR, f"{date or _today()}.json")


def open_positions():
    from stockscout3.regime  import get_regime
    from stockscout3.scorer  import score_universe, top_picks

    print(f"\n{'='*50}")
    print(f"StockScout 3 — OPEN  {_today()} 09:30")
    print(f"{'='*50}")

    # 1. Regime check
    regime_mult, regime_label, regime_detail = get_regime()
    if regime_mult == 0.0:
        print(f"\n🚫 BEARISH regime — skipping all positions today")
        rec = {"date": _today(), "action": "open", "skipped": True,
               "reason": "BEARISH regime", "regime": regime_detail}
        json.dump(rec, open(_trade_path(), "w"), indent=2)
        return

    trade_size = TRADE_SIZE_FULL * regime_mult
    print(f"\n📊 Regime: {regime_label} (mult={regime_mult}) — ${trade_size:.0f}/position")

    # 2. Score universe
    print("\nScoring universe...")
    df = score_universe(verbose=False)
    picks = top_picks(df, n=N_POSITIONS)

    if picks.empty:
        print("No picks after gap filter — skipping")
        return

    # 3. Get live open prices
    positions = []
    for _, row in picks.iterrows():
        tkr = row["ticker"]
        try:
            info = yf.Ticker(tkr).fast_info
            price = float(info.last_price)
            shares = int(trade_size // price)
            if shares < 1:
                continue
            positions.append({
                "ticker": tkr, "shares": shares, "entry_price": price,
                "cost": round(shares * price, 2),
                "vst": row["vst"], "score": row["score"],
            })
            print(f"   BUY  {tkr:6s}  {shares}sh @ ${price:.2f}  (${shares*price:.0f})")
        except Exception as e:
            print(f"   {tkr}: price error — {e}")

    record = {
        "date": _today(), "action": "open",
        "regime": regime_label, "regime_mult": regime_mult,
        "positions": positions,
    }
    json.dump(record, open(_trade_path(), "w"), indent=2)
    print(f"\n✅ {len(positions)} positions opened — saved {_trade_path()}")


def close_positions():
    path = _trade_path()
    if not os.path.exists(path):
        print(f"No open file for {_today()} — nothing to close")
        return

    rec = json.load(open(path))
    if rec.get("skipped") or not rec.get("positions"):
        print("No open positions to close")
        return

    print(f"\n{'='*50}")
    print(f"StockScout 3 — CLOSE {_today()} 16:00")
    print(f"{'='*50}\n")

    total_pnl = 0.0
    for pos in rec["positions"]:
        tkr = pos["ticker"]
        try:
            price = float(yf.Ticker(tkr).fast_info.last_price)
            pnl = (price - pos["entry_price"]) * pos["shares"]
            pos["exit_price"] = price
            pos["pnl"] = round(pnl, 2)
            total_pnl += pnl
            icon = "🟢" if pnl >= 0 else "🔴"
            print(f"   {icon} {tkr:6s}  exit ${price:.2f}  P&L ${pnl:+.2f}")
        except Exception as e:
            print(f"   {tkr}: close error — {e}")

    rec["action"] = "closed"
    rec["total_pnl"] = round(total_pnl, 2)
    json.dump(rec, open(path, "w"), indent=2)

    icon = "🟢" if total_pnl >= 0 else "🔴"
    print(f"\n{icon} Day P&L: ${total_pnl:+.2f}")
    print(f"✅ Saved {path}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    if cmd == "open":
        open_positions()
    elif cmd == "close":
        close_positions()
    else:
        print(f"Usage: python -m stockscout3.portfolio [open|close]")
