"""
dashboard.py — Generates the StockScout 3 live dashboard HTML
Reads: data/scores_latest.json, data/trades/*.json, data/trump_predictions.json
Outputs: data/dashboard.html
"""
import json, os, glob, datetime
import collections

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def load(path, default=None):
    try: return json.load(open(path))
    except: return default

def regime_today():
    trump = load(os.path.join(DATA_DIR, "trump_predictions.json"), [])
    if not trump:
        return "NEUTRAL", "No data", "#8b949e"
    today = str(datetime.date.today())
    todays = [p for p in trump if str(p.get("date_signal",""))[:10] == today]
    if not todays:
        return "NEUTRAL", "No signal today", "#8b949e"
    DIR_MAP = {"LONG":"BULLISH","UP":"BULLISH","SHORT":"BEARISH","DOWN":"BEARISH",
               "VOLATILE":"NEUTRAL","NEUTRAL":"NEUTRAL"}
    votes = [DIR_MAP.get(str(p.get("direction","")).upper(),"NEUTRAL") for p in todays]
    cnt = collections.Counter(votes)
    if cnt["BEARISH"] > 0 and cnt["BULLISH"] == 0:
        label = "BEARISH"
    else:
        label = cnt.most_common(1)[0][0]
    models = list({p.get("model_name","") for p in todays})
    color = {"BULLISH":"#22c55e","NEUTRAL":"#f59e0b","BEARISH":"#ef4444"}[label]
    detail = f"{len(todays)} models: {', '.join(models[:3])}"
    return label, detail, color

def build():
    scores = load(os.path.join(DATA_DIR, "scores_latest.json"), [])
    trade_files = sorted(glob.glob(os.path.join(DATA_DIR, "trades", "*.json")), reverse=True)
    trades = [load(f) for f in trade_files[:30] if load(f)]

    today = str(datetime.date.today())
    open_trade = next((t for t in trades if t.get("date") == today and t.get("action") == "open"), None)
    closed_trades = [t for t in trades if t.get("action") == "closed"]

    total_pnl = sum(t.get("total_pnl", 0) for t in closed_trades)
    win_days = sum(1 for t in closed_trades if t.get("total_pnl", 0) > 0)
    hit_rate = win_days / len(closed_trades) * 100 if closed_trades else 0

    regime_label, regime_detail, regime_color = regime_today()

    # Scores table rows
    score_rows = ""
    if scores:
        for i, s in enumerate(scores[:20]):
            gapped = s.get("gapped", False)
            pick = i < 5 and not gapped
            row_class = "pick" if pick else ("gapped" if gapped else "")
            badge = '<span class="badge-pick">PICK</span>' if pick else ('<span class="badge-gap">GAP</span>' if gapped else "")
            score_rows += f"""<tr class="{row_class}">
  <td>{s['ticker']} {badge}</td>
  <td>{s.get('score',0):.3f}</td>
  <td>{s.get('vst',0):.2f}</td>
  <td>{'+' if s.get('rs',0)>=0 else ''}{s.get('rs',0):.3f}</td>
  <td>{'+' if s.get('rt',0)>=0 else ''}{s.get('rt',0):.3f}</td>
  <td>{'+' if s.get('gap_pct',0)>=0 else ''}{s.get('gap_pct',0)*100:.2f}%</td>
</tr>"""

    # Open positions
    pos_html = ""
    if open_trade and open_trade.get("positions"):
        for p in open_trade["positions"]:
            pos_html += f"""<tr>
  <td><b>{p['ticker']}</b></td>
  <td>${p['entry_price']:.2f}</td>
  <td>{p['shares']}</td>
  <td>${p['cost']:.0f}</td>
  <td class="neutral">OPEN</td>
</tr>"""
    elif open_trade and open_trade.get("skipped"):
        pos_html = f'<tr><td colspan="5" style="color:#ef4444;text-align:center">&#x1F6AB; Skipped — {open_trade.get("reason","BEARISH regime")}</td></tr>'
    else:
        pos_html = '<tr><td colspan="5" style="color:#6b7280;text-align:center">No open positions today</td></tr>'

    # Trade history
    hist_rows = ""
    for t in closed_trades[:15]:
        pnl = t.get("total_pnl", 0)
        tickers = ", ".join(p["ticker"] for p in t.get("positions",[]))
        hist_rows += f"""<tr>
  <td>{t['date']}</td>
  <td style="font-size:.75rem;color:#8b949e">{tickers[:40]}</td>
  <td class="{'up' if pnl>=0 else 'down'}">${pnl:+.2f}</td>
  <td style="color:#8b949e">{t.get('regime','—')}</td>
</tr>"""

    # Equity curve data
    eq_dates = json.dumps([t["date"] for t in reversed(closed_trades)])
    eq_cum   = []
    running  = 0.0
    for t in reversed(closed_trades):
        running += t.get("total_pnl", 0)
        eq_cum.append(round(running, 2))
    eq_vals = json.dumps(eq_cum)

    score_updated = load(os.path.join(DATA_DIR, "scores_latest.json"))
    score_time = today

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockScout 3</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:20px;max-width:1200px;margin:0 auto}}
header{{padding:16px 0 24px;border-bottom:1px solid #30363d;margin-bottom:24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
header h1{{font-size:1.5rem}}header h1 span{{color:#8b949e;font-size:.9rem;margin-left:8px}}
.nav a{{color:#58a6ff;font-size:.8rem;text-decoration:none;background:#161b22;border:1px solid #30363d;padding:4px 10px;border-radius:6px;margin-right:6px}}
.nav a:hover{{border-color:#58a6ff}}
#updated{{font-size:.75rem;color:#6b7280;margin-left:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px}}
.card h2{{font-size:.85rem;color:#8b949e;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.kpis{{display:flex;gap:16px;flex-wrap:wrap}}
.kpi{{flex:1;min-width:80px}}
.kpi-val{{font-size:1.4rem;font-weight:700}}
.kpi-label{{font-size:.7rem;color:#8b949e;margin-top:2px}}
.regime-box{{display:flex;align-items:center;gap:12px}}
.regime-badge{{font-size:1.1rem;font-weight:700;padding:6px 14px;border-radius:6px}}
.regime-detail{{font-size:.75rem;color:#8b949e}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th{{color:#8b949e;font-size:.72rem;padding:8px 10px;text-align:left;border-bottom:1px solid #21262d}}
td{{padding:7px 10px;border-bottom:1px solid #161b22}}
tr:hover td{{background:#161b22}}
tr.pick td{{color:#22c55e}}
tr.gapped td{{color:#6b7280}}
.badge-pick{{background:#22c55e22;color:#22c55e;font-size:.6rem;padding:1px 5px;border-radius:3px;margin-left:4px}}
.badge-gap{{background:#ef444422;color:#ef4444;font-size:.6rem;padding:1px 5px;border-radius:3px;margin-left:4px}}
.up{{color:#22c55e}}.down{{color:#ef4444}}.neutral{{color:#8b949e}}
.full{{grid-column:1/-1}}
</style>
</head>
<body>
<header>
  <h1>&#128270; StockScout 3 <span>Regime-Gated Momentum Scorer</span></h1>
  <div class="nav">
    <a href="/stockscout/">v1</a>
    <a href="/stockscout2/">v2</a>
    <a href="/stockscout3/backtest/">Backtest</a>
    <a href="https://github.com/menonpg/stockscout3" target="_blank">GitHub</a>
  </div>
  <div id="updated">Scores: {score_time}</div>
</header>

<div class="grid">

  <!-- Regime Card -->
  <div class="card">
    <h2>&#127968; Macro Regime (Trump Code)</h2>
    <div class="regime-box">
      <div class="regime-badge" style="background:{regime_color}22;color:{regime_color}">{regime_label}</div>
      <div class="regime-detail">{regime_detail}</div>
    </div>
    <div style="margin-top:12px;font-size:.72rem;color:#6b7280">
      Source: sstklen/trump-code &middot; Updated daily
    </div>
  </div>

  <!-- KPI Card -->
  <div class="card">
    <h2>&#128200; Performance</h2>
    <div class="kpis">
      <div class="kpi">
        <div class="kpi-val {'up' if total_pnl>=0 else 'down'}">${total_pnl:+,.0f}</div>
        <div class="kpi-label">Total P&amp;L</div>
      </div>
      <div class="kpi">
        <div class="kpi-val">{len(closed_trades)}</div>
        <div class="kpi-label">Days traded</div>
      </div>
      <div class="kpi">
        <div class="kpi-val">{hit_rate:.0f}%</div>
        <div class="kpi-label">Win rate</div>
      </div>
    </div>
  </div>

  <!-- Equity Curve -->
  <div class="card">
    <h2>&#128185; Equity Curve</h2>
    <canvas id="equity" height="80"></canvas>
  </div>

</div>

<!-- Today's Positions -->
<div class="card" style="margin-bottom:16px">
  <h2>&#128197; Today's Positions — {today}</h2>
  <table>
    <thead><tr><th>Ticker</th><th>Entry</th><th>Shares</th><th>Cost</th><th>Status</th></tr></thead>
    <tbody>{pos_html}</tbody>
  </table>
</div>

<!-- Scores Table -->
<div class="card" style="margin-bottom:16px">
  <h2>&#128202; Today's Scores (Top 20)</h2>
  <table>
    <thead><tr><th>Ticker</th><th>Score</th><th>VST</th><th>RS</th><th>RT</th><th>Gap</th></tr></thead>
    <tbody>{score_rows if score_rows else '<tr><td colspan="6" style="color:#6b7280;text-align:center">Run score workflow to populate</td></tr>'}</tbody>
  </table>
</div>

<!-- Trade History -->
<div class="card">
  <h2>&#128203; Trade History</h2>
  <table>
    <thead><tr><th>Date</th><th>Tickers</th><th>P&amp;L</th><th>Regime</th></tr></thead>
    <tbody>{hist_rows if hist_rows else '<tr><td colspan="4" style="color:#6b7280;text-align:center">No closed trades yet</td></tr>'}</tbody>
  </table>
</div>

<script>
new Chart(document.getElementById('equity'), {{
  type:'line',
  data:{{
    labels:{eq_dates},
    datasets:[{{
      data:{eq_vals},
      borderColor:'#22c55e',
      backgroundColor:'#22c55e22',
      fill:true, pointRadius:0, tension:0.3
    }}]
  }},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{grid:{{color:'#30363d'}},ticks:{{color:'#8b949e',callback:v=>'$'+v}}}},
      x:{{ticks:{{color:'#8b949e',maxTicksLimit:8}},grid:{{display:false}}}}
    }}
  }}
}});
</script>
</body>
</html>"""

    out = os.path.join(DATA_DIR, "dashboard.html")
    open(out, "w").write(html)
    print(f"Dashboard saved: {out}")


if __name__ == "__main__":
    build()
