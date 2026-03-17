# StockScout 3

Momentum + macro regime scorer for US equities. No server required — runs entirely on GitHub Actions.

## Architecture

```
Trump Code regime gate (macro: bullish / neutral / bearish)
    ↓
VST + RS + RT momentum scorer (S&P 100)
    ↓
Gap filter (skip if open > prior_close × 1.005)
    ↓
Position sizing (full / half / skip by regime)
    ↓
Open at 9:30 AM → Close at 4:00 PM
```

## Signals

| Signal | Description |
|---|---|
| VST | Volume Surge Trend: avg_vol_5d / avg_vol_20d |
| RS | Relative Strength: stock 20d return vs SPY |
| RT | Recent Trend: 5d return |
| Gap | Skip if open > prior_close × 1.005 |
| Regime | Trump Code macro signal: 1.0 / 0.5 / 0.0 |

## Backtest Results (StockScout 2 baseline)

| Strategy | Return | Sharpe | Max DD |
|---|---|---|---|
| Equal + gap<0.5% | +32.9% | 1.26 | 13.3% |
| Equal baseline | +15.4% | 0.58 | 17.4% |
| SPY | +43.7% | — | — |

Regime gate expected to reduce drawdown on bearish macro days.

## Schedules (GitHub Actions)

| Workflow | Time (EST) | Action |
|---|---|---|
| score.yml | 8:30 AM Mon-Fri | Score S&P 100 |
| open.yml | 9:30 AM Mon-Fri | Open top 5 positions |
| close.yml | 4:00 PM Mon-Fri | Close + log P&L |

## Setup

1. Fork this repo
2. Add `FINNHUB_API_KEY` to repo secrets
3. Enable GitHub Actions
4. Done — no server, no crond, no phone needed
