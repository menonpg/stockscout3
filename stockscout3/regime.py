"""
regime.py — Trump Code macro regime gate for StockScout 3

Fetches today's prediction from the trump-code project (sstklen/trump-code).
Returns a regime multiplier: 1.0 (bullish), 0.5 (neutral), 0.0 (bearish).

Data source: https://raw.githubusercontent.com/sstklen/trump-code/main/data/predictions_log.json
Falls back to NEUTRAL (0.5) on any fetch/parse error — fail safe, not fail hard.
"""

import requests, json, datetime, os

PREDICTIONS_URL = "https://raw.githubusercontent.com/sstklen/trump-code/main/data/predictions_log.json"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "regime_cache.json")

BULLISH  = 1.0
NEUTRAL  = 0.5
BEARISH  = 0.0

REGIME_LABELS = {BULLISH: "BULLISH", NEUTRAL: "NEUTRAL", BEARISH: "BEARISH"}


def _load_cache():
    try:
        c = json.load(open(CACHE_FILE))
        if c.get("date") == str(datetime.date.today()):
            return c
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    json.dump(data, open(CACHE_FILE, "w"), indent=2)


def get_regime(verbose=True) -> tuple[float, str, dict]:
    """
    Returns (multiplier, label, detail_dict).
    multiplier: 1.0 / 0.5 / 0.0
    label: 'BULLISH' / 'NEUTRAL' / 'BEARISH'
    detail: raw prediction record for today
    """
    cached = _load_cache()
    if cached:
        m = cached["multiplier"]
        if verbose:
            print(f"   [regime] {REGIME_LABELS[m]} (cached) — {cached.get('signal','')}")
        return m, REGIME_LABELS[m], cached

    try:
        r = requests.get(PREDICTIONS_URL, timeout=10)
        r.raise_for_status()
        log = r.json()
    except Exception as e:
        if verbose:
            print(f"   [regime] NEUTRAL (fetch failed: {e})")
        return NEUTRAL, "NEUTRAL", {"error": str(e)}

    today = str(datetime.date.today())
    # predictions_log is a list of records [{date, signal, direction, confidence, ...}]
    # find today's most recent entry
    todays = [p for p in log if str(p.get("date", ""))[:10] == today]

    if not todays:
        # No prediction today yet — treat as neutral
        if verbose:
            print(f"   [regime] NEUTRAL (no prediction for {today})")
        return NEUTRAL, "NEUTRAL", {"note": "no prediction today"}

    # Use most recent
    pred = todays[-1]
    direction = str(pred.get("direction", "")).upper()
    confidence = float(pred.get("confidence", 0.5))

    if direction == "UP" and confidence >= 0.6:
        multiplier = BULLISH
    elif direction == "DOWN" and confidence >= 0.6:
        multiplier = BEARISH
    else:
        multiplier = NEUTRAL

    record = {
        "date": today,
        "multiplier": multiplier,
        "signal": pred.get("signal", ""),
        "direction": direction,
        "confidence": confidence,
        "raw": pred,
    }
    _save_cache(record)

    label = REGIME_LABELS[multiplier]
    if verbose:
        print(f"   [regime] {label} (confidence={confidence:.0%}, signal={pred.get('signal','')})")
    return multiplier, label, record


if __name__ == "__main__":
    m, label, detail = get_regime(verbose=True)
    print(json.dumps(detail, indent=2, default=str))
