"""
regime.py — Trump Code macro regime gate for StockScout 3

Fetches predictions from sstklen/trump-code predictions_log.json.
Multiple models fire per day — we aggregate by majority vote.

Returns regime multiplier: 1.0 (BULLISH), 0.5 (NEUTRAL), 0.0 (BEARISH)
Falls back to NEUTRAL on any error.
"""

import requests, json, datetime, os, collections

PREDICTIONS_URL = "https://raw.githubusercontent.com/sstklen/trump-code/main/data/predictions_log.json"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "regime_cache.json")

BULLISH = 1.0
NEUTRAL = 0.5
BEARISH = 0.0
LABELS  = {BULLISH: "BULLISH", NEUTRAL: "NEUTRAL", BEARISH: "BEARISH"}

# direction strings from trump-code → our signal
DIR_MAP = {
    "LONG":     BULLISH,
    "UP":       BULLISH,
    "SHORT":    BEARISH,
    "DOWN":     BEARISH,
    "VOLATILE": NEUTRAL,
    "NEUTRAL":  NEUTRAL,
}


def _load_cache(date_str):
    try:
        c = json.load(open(CACHE_FILE))
        if c.get("date") == date_str:
            return c
    except Exception:
        pass
    return None


def _save_cache(data):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    json.dump(data, open(CACHE_FILE, "w"), indent=2)


def _aggregate(preds: list) -> tuple[float, str]:
    """Majority vote across all model predictions for a day."""
    votes = [DIR_MAP.get(str(p.get("direction","")).upper(), NEUTRAL) for p in preds]
    counts = collections.Counter(votes)
    # If any BEARISH signal exists alongside no BULLISH → lean bearish
    if counts[BEARISH] > 0 and counts[BULLISH] == 0:
        return BEARISH, "BEARISH"
    winner = counts.most_common(1)[0][0]
    return winner, LABELS[winner]


def get_regime(date_str=None, log_data=None, verbose=True) -> tuple[float, str, dict]:
    """
    Returns (multiplier, label, detail).
    date_str: 'YYYY-MM-DD', defaults to today.
    log_data: pre-loaded list (for backtest use), else fetches from GitHub.
    """
    if date_str is None:
        date_str = str(datetime.date.today())

    cached = _load_cache(date_str)
    if cached and log_data is None:
        m = cached["multiplier"]
        if verbose:
            print(f"   [regime] {LABELS[m]} (cached) signal={cached.get('signals')}")
        return m, LABELS[m], cached

    if log_data is None:
        try:
            r = requests.get(PREDICTIONS_URL, timeout=10)
            r.raise_for_status()
            log_data = r.json()
        except Exception as e:
            if verbose:
                print(f"   [regime] NEUTRAL (fetch failed: {e})")
            return NEUTRAL, "NEUTRAL", {"error": str(e)}

    todays = [p for p in log_data if str(p.get("date_signal",""))[:10] == date_str]

    if not todays:
        if verbose:
            print(f"   [regime] NEUTRAL (no predictions for {date_str})")
        return NEUTRAL, "NEUTRAL", {"note": "no predictions"}

    multiplier, label = _aggregate(todays)
    signals = list({p.get("model_name","") for p in todays})
    directions = [str(p.get("direction","")) for p in todays]

    record = {
        "date": date_str, "multiplier": multiplier,
        "label": label, "signals": signals,
        "directions": directions, "n_models": len(todays),
    }
    if log_data is None:
        _save_cache(record)

    if verbose:
        print(f"   [regime] {label} ({len(todays)} models: {collections.Counter(directions)})")
    return multiplier, label, record


if __name__ == "__main__":
    m, label, detail = get_regime(verbose=True)
    print(json.dumps(detail, indent=2, default=str))
