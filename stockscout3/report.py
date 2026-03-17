"""
report.py — StockScout 3 backtest dashboard
Generates stockscout3_report.html comparing baseline vs regime-gated results.
"""
import json, os, datetime
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load(path):
    try:
        return json.load(open(path))
    except:
        return None


def kpi_card(label, value, sub="", color="#f59e0b"):
    return f"""<div class="kpi"><div class="kpi-val" style="color:{color}">{value}</div>
<div class="kpi-label">{label}</div>{f'<div class="kpi-sub">{sub}</div>' if sub else ''}</div>"""


def cum_chart(daily, canvas_id, color):
    dates = json.dumps([d["date"] for d in daily])
    pnls  = [d["pnl"] for d in daily]
    cum   = list(np.cumsum(pnls))
    vals  = json.dumps([round(v, 2) for v in cum])
    return f"""
new Chart(document.getElementById('{canvas_id}'), {{
  type:'line',
  data:{{labels:{dates},datasets:[{{
    label:'Cumulative P&L ($)', data:{vals},
    borderColor:'{color}', backgroundColor:'{color}22',
    fill:true, pointRadius:0, tension:0.3
  }}]}},
  options:{{responsive:true, plugins:{{legend:{{display:false}}}},
    scales:{{y:{{grid:{{color:'#30363d'}}, ticks:{{color:'#8b949e'}}}},
             x:{{ticks:{{color:'#8b949e', maxTicksLimit:12}}, grid:{{display:false}}}}}}}}
}});"""


def build():
    baseline = load(os.path.join(DATA_DIR, "backtest_baseline.json"))
    regime   = load(os.path.join(DATA_DIR, "backtest_regime.json"))

    if not baseline:
        print("No backtest_baseline.json found"); return

    b, r = baseline, regime or {}
    today = str(datetime.date.today())

    b_kpis = f"""
{kpi_card("Return", f"{b['return_pct']:+.2f}%", "gap&lt;0.5% filter", "#f59e0b")}
{kpi_card("SPY", f"{b['spy_pct']:+.2f}%", "benchmark", "#6b7280")}
{kpi_card("Sharpe", f"{b['sharpe']:.3f}", "", "#f59e0b")}
{kpi_card("Max DD", f"${b['max_drawdown_dollars']:,.0f}", "", "#ef4444")}
{kpi_card("Trades", str(b['total_trades']), f"Hit rate {b['hit_rate_pct']:.1f}%", "#f59e0b")}"""

    r_kpis = f"""
{kpi_card("Return", f"{r.get('return_pct',0):+.2f}%", "regime gate ON", "#22c55e")}
{kpi_card("SPY", f"{r.get('spy_pct', b['spy_pct']):+.2f}%", "benchmark", "#6b7280")}
{kpi_card("Sharpe", f"{r.get('sharpe',0):.3f}", "", "#22c55e")}
{kpi_card("Max DD", f"${r.get('max_drawdown_dollars',0):,.0f}", "", "#ef4444")}
{kpi_card("Bearish skip", str(r.get('bearish_days_skipped',0)), "days avoided", "#22c55e")}""" if r else ""

    charts = ""
    if b.get("daily"):
        charts += f"<canvas id='b_cum' height='80'></canvas>"
    if r.get("daily"):
        charts += f"<canvas id='r_cum' height='80'></canvas>"

    chart_js = ""
    if b.get("daily"):
        chart_js += cum_chart(b["daily"], "b_cum", "#f59e0b")
    if r.get("daily"):
        chart_js += cum_chart(r["daily"], "r_cum", "#22c55e")

    trade_rows = ""
    for t in (b.get("trades") or [])[:50]:
        pnl = t.get("pnl", 0)
        trade_rows += (f'<tr><td>{t["date"]}</td><td><b>{t["ticker"]}</b></td>'
                       f'<td>{t["shares"]}</td><td>${t["entry"]:.2f}</td>'
                       f'<td>${t["exit"]:.2f}</td>'
                       f'<td class="{"up" if pnl>=0 else "down"}">${pnl:+.2f}</td></tr>')
    if not trade_rows:
        trade_rows = '<tr><td colspan="6" style="color:#6b7280;text-align:center">No trades</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockScout 3 Backtest</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:20px}}
header{{padding:20px 0 30px;border-bottom:1px solid #30363d;margin-bottom:30px}}
header h1{{font-size:1.6rem;color:#e6edf3}}header h1 span{{color:#8b949e;font-size:1rem;margin-left:10px}}
.links a{{color:#58a6ff;font-size:.8rem;text-decoration:none;margin-right:16px}}
.links a:hover{{text-decoration:underline}}
.section{{margin-bottom:40px}}
h2{{font-size:1.1rem;color:#8b949e;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;min-width:120px}}
.kpi-val{{font-size:1.5rem;font-weight:700;margin-bottom:4px}}
.kpi-label{{font-size:.75rem;color:#8b949e}}
.kpi-sub{{font-size:.7rem;color:#6b7280;margin-top:2px}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.chart-box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px}}
.chart-box h3{{font-size:.85rem;color:#8b949e;margin-bottom:12px}}
.compare{{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}}
.compare table{{width:100%;border-collapse:collapse}}
.compare th{{background:#21262d;color:#8b949e;font-size:.75rem;padding:10px 16px;text-align:left}}
.compare td{{padding:10px 16px;font-size:.85rem;border-top:1px solid #21262d}}
.up{{color:#22c55e}}.down{{color:#ef4444}}.neutral{{color:#8b949e}}
.tag{{font-size:.65rem;background:#21262d;border-radius:4px;padding:2px 6px;margin-left:6px;color:#8b949e}}
</style>
</head>
<body>
<header>
  <h1>&#128270; StockScout 3 <span>Regime Gate Backtest</span></h1>
  <div style="margin-top:8px" class="links">
    <a href="/stockscout/">v1 Live</a>
    <a href="/stockscout2/">v2 Live</a>
    <a href="/backtest/">v2 Backtest</a>
    <a href="https://github.com/menonpg/stockscout3" target="_blank">GitHub</a>
  </div>
  <div style="margin-top:10px;font-size:.75rem;color:#6b7280">Updated {today} &middot; {b['start']} to {b['end']}</div>
</header>

<div class="section">
  <h2>Baseline — VST+RS+RT + Gap Filter <span class="tag">no regime gate</span></h2>
  <div class="kpis">{b_kpis}</div>
</div>

{'<div class="section"><h2>Regime Gate ON <span class="tag">Trump Code macro filter</span></h2><div class="kpis">' + r_kpis + '</div></div>' if r_kpis else ''}

<div class="section">
  <h2>Comparison</h2>
  <div class="compare">
    <table>
      <thead><tr><th>Metric</th><th>Baseline</th>{'<th>Regime Gate</th>' if r else ''}<th>SPY</th></tr></thead>
      <tbody>
        <tr><td>Return</td>
            <td class="{'up' if b['return_pct']>0 else 'down'}">{b['return_pct']:+.2f}%</td>
            {'<td class="' + ("up" if r.get("return_pct",0)>0 else "down") + '">' + f"{r.get('return_pct',0):+.2f}%" + '</td>' if r else ''}
            <td class="neutral">{b['spy_pct']:+.2f}%</td></tr>
        <tr><td>Sharpe</td>
            <td>{b['sharpe']:.3f}</td>
            {'<td>' + f"{r.get('sharpe',0):.3f}" + '</td>' if r else ''}
            <td class="neutral">--</td></tr>
        <tr><td>Max Drawdown</td>
            <td class="down">${b['max_drawdown_dollars']:,.0f}</td>
            {'<td class="down">$' + f"{r.get('max_drawdown_dollars',0):,.0f}" + '</td>' if r else ''}
            <td class="neutral">--</td></tr>
        <tr><td>Total Trades</td>
            <td>{b['total_trades']}</td>
            {'<td>' + str(r.get('total_trades',0)) + '</td>' if r else ''}
            <td class="neutral">--</td></tr>
        <tr><td>Hit Rate</td>
            <td>{b['hit_rate_pct']:.1f}%</td>
            {'<td>' + f"{r.get('hit_rate_pct',0):.1f}%" + '</td>' if r else ''}
            <td class="neutral">--</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="section">
  <h2>Equity Curves</h2>
  <div class="charts">
    <div class="chart-box"><h3>Baseline (amber)</h3><canvas id="b_cum" height="100"></canvas></div>
    {'<div class="chart-box"><h3>Regime Gate (green)</h3><canvas id="r_cum" height="100"></canvas></div>' if r.get('daily') else ''}
  </div>
</div>

<script>
{chart_js}
</script>

<div class="section" style="margin-top:24px">
  <h2>&#128203; Baseline Trade Book (first 50)</h2>
  <div class="compare">
    <table>
      <thead><tr><th>Date</th><th>Ticker</th><th>Shares</th><th>Entry</th><th>Exit</th><th>P&amp;L</th></tr></thead>
      <tbody>{{trade_rows}}</tbody>
    </table>
  </div>
</div>

</body>
</html>"""

    out = os.path.join(DATA_DIR, "stockscout3_report.html")
    open(out, "w").write(html)
    print(f"Report saved: {out}")


if __name__ == "__main__":
    build()
