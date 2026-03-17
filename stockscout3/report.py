"""report.py — StockScout 3 backtest dashboard"""
import json, os, datetime
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def load(path):
    try: return json.load(open(path))
    except: return None

def kpi(label, value, sub="", color="#f59e0b"):
    return (f'<div class="kpi"><div class="kpi-val" style="color:{color}">{value}</div>'
            f'<div class="kpi-label">{label}</div>'
            + (f'<div class="kpi-sub">{sub}</div>' if sub else '') + '</div>')

def cum_chart(daily, cid, color):
    dates = json.dumps([d["date"] for d in daily])
    cum   = json.dumps([round(d["cumulative_pnl"],2) for d in daily])
    return f"""new Chart(document.getElementById('{cid}'),{{type:'line',
  data:{{labels:{dates},datasets:[{{data:{cum},borderColor:'{color}',
    backgroundColor:'{color}22',fill:true,pointRadius:0,tension:0.3}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},
    scales:{{y:{{grid:{{color:'#30363d'}},ticks:{{color:'#8b949e',callback:v=>'$'+v.toLocaleString()}}}},
             x:{{ticks:{{color:'#8b949e',maxTicksLimit:12}},grid:{{display:false}}}}}}}}
}});"""

def trade_rows(result, n=100):
    rows = ""
    trades = result.get("trades", [])
    for t in trades[:n]:
        pnl = t.get("pnl", 0)
        cls = "up" if pnl >= 0 else "down"
        rows += (f'<tr><td>{t.get("date","")}</td><td><b>{t["ticker"]}</b></td>'
                 f'<td>{t.get("vst",0):.2f}</td>'
                 f'<td>${t.get("open",0):.2f}</td><td>${t.get("close",0):.2f}</td>'
                 f'<td>{t.get("ret_pct",0):+.2f}%</td>'
                 f'<td class="{cls}">${pnl:+.2f}</td></tr>')
    return rows or '<tr><td colspan="7" style="color:#6b7280;text-align:center">No trades</td></tr>'

def bw_rows(days):
    rows = ""
    for d in days:
        pnl = d.get("day_pnl",0)
        tickers = ", ".join(t["ticker"] for t in d.get("picks",[]))
        rows += (f'<tr><td>{d["date"]}</td>'
                 f'<td style="font-size:.75rem;color:#8b949e">{tickers}</td>'
                 f'<td class="{"up" if pnl>=0 else "down"}">${pnl:+.2f}</td></tr>')
    return rows

def build():
    b_raw = load(os.path.join(DATA_DIR, "backtest_baseline.json"))
    r_raw = load(os.path.join(DATA_DIR, "backtest_regime.json"))
    if not b_raw:
        print("No backtest_baseline.json"); return

    b = b_raw["summary"]
    r = r_raw["summary"] if r_raw else {}
    today = str(datetime.date.today())

    b_color = "#22c55e" if b["total_pnl"] >= 0 else "#ef4444"
    r_color = "#22c55e" if r.get("total_pnl",0) >= 0 else "#ef4444"

    b_kpis = (kpi("Return", f"{b['total_pnl_pct']:+.2f}%", f"${b['total_pnl']:+,.0f}", b_color) +
              kpi("SPY", f"{b['spy_pct']:+.2f}%", "benchmark", "#6b7280") +
              kpi("Sharpe", f"{b['sharpe_annualized']:.3f}", "", "#f59e0b") +
              kpi("Max DD", f"${b['max_drawdown']:,.0f}", "", "#ef4444") +
              kpi("Trades", str(b['total_trades']), f"Hit {b['hit_rate_pct']:.1f}%", "#f59e0b"))

    r_kpis = (kpi("Return", f"{r['total_pnl_pct']:+.2f}%", f"${r['total_pnl']:+,.0f}", r_color) +
              kpi("SPY", f"{r['spy_pct']:+.2f}%", "benchmark", "#6b7280") +
              kpi("Sharpe", f"{r['sharpe_annualized']:.3f}", "", "#22c55e") +
              kpi("Max DD", f"${r['max_drawdown']:,.0f}", "", "#ef4444") +
              kpi("Bearish skip", str(r.get('bearish_days_skipped',0)), "days avoided", "#22c55e")
              ) if r else ""

    chart_js = cum_chart(b_raw["daily"], "b_cum", "#f59e0b")
    if r_raw:
        chart_js += cum_chart(r_raw["daily"], "r_cum", "#22c55e")

    cmp_regime = (f'<th>Regime Gate</th>' if r else '')
    cmp_rows = ""
    metrics = [
        ("Return", f"{b['total_pnl_pct']:+.2f}%", f"{r.get('total_pnl_pct',0):+.2f}%" if r else "", f"{b['spy_pct']:+.2f}%"),
        ("P&L ($)", f"${b['total_pnl']:+,.0f}", f"${r.get('total_pnl',0):+,.0f}" if r else "", "—"),
        ("Sharpe", f"{b['sharpe_annualized']:.3f}", f"{r.get('sharpe_annualized',0):.3f}" if r else "", "—"),
        ("Max DD", f"${b['max_drawdown']:,.0f}", f"${r.get('max_drawdown',0):,.0f}" if r else "", "—"),
        ("Trades", str(b["total_trades"]), str(r.get("total_trades",0)) if r else "", "—"),
        ("Hit Rate", f"{b['hit_rate_pct']:.1f}%", f"{r.get('hit_rate_pct',0):.1f}%" if r else "", "—"),
    ]
    for m in metrics:
        td_r = f"<td>{m[2]}</td>" if r else ""
        cmp_rows += f"<tr><td>{m[0]}</td><td>{m[1]}</td>{td_r}<td class='neutral'>{m[3]}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockScout 3 Backtest</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:20px;max-width:1200px;margin:0 auto}}
header{{padding:16px 0 24px;border-bottom:1px solid #30363d;margin-bottom:28px}}
header h1{{font-size:1.5rem}}header h1 span{{color:#8b949e;font-size:.9rem;margin-left:8px}}
.links a{{color:#58a6ff;font-size:.8rem;text-decoration:none;background:#161b22;border:1px solid #30363d;padding:4px 10px;border-radius:6px;margin-right:6px}}
.section{{margin-bottom:32px}}
h2{{font-size:1rem;color:#8b949e;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.tag{{font-size:.65rem;background:#21262d;border-radius:4px;padding:2px 6px;margin-left:6px;color:#8b949e}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 18px;min-width:110px}}
.kpi-val{{font-size:1.4rem;font-weight:700;margin-bottom:3px}}
.kpi-label{{font-size:.72rem;color:#8b949e}}.kpi-sub{{font-size:.68rem;color:#6b7280;margin-top:2px}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.chart-box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px}}
.chart-box h3{{font-size:.82rem;color:#8b949e;margin-bottom:10px}}
.tbl{{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th{{background:#21262d;color:#8b949e;font-size:.72rem;padding:9px 12px;text-align:left}}
td{{padding:8px 12px;border-top:1px solid #21262d}}
tr:hover td{{background:#1c2128}}
.up{{color:#22c55e}}.down{{color:#ef4444}}.neutral{{color:#8b949e}}
</style></head><body>
<header>
  <h1>&#128270; StockScout 3 <span>Backtest — Baseline vs Regime Gate</span></h1>
  <div style="margin-top:10px" class="links">
    <a href="/stockscout3/">Live Dashboard</a>
    <a href="/stockscout/">v1</a><a href="/stockscout2/">v2</a>
    <a href="/backtest/">v2 Backtest</a>
    <a href="https://github.com/menonpg/stockscout3" target="_blank">GitHub</a>
  </div>
  <div style="margin-top:8px;font-size:.72rem;color:#6b7280">
    {b['backtest_start']} &rarr; {b['backtest_end']} &middot; Capital ${b['total_capital']:,} &middot; {b['top_n']} positions &times; ${b['position_size']:,} &middot; Updated {today}
  </div>
</header>

<div class="section">
  <h2>Baseline &mdash; VST+RS+RT + Gap Filter <span class="tag">no regime gate</span></h2>
  <div class="kpis">{b_kpis}</div>
</div>

{'<div class="section"><h2>Regime Gate ON <span class="tag">Trump Code macro filter</span></h2><div class="kpis">' + r_kpis + '</div></div>' if r_kpis else ''}

<div class="section">
  <h2>Equity Curves</h2>
  <div class="charts">
    <div class="chart-box"><h3>Baseline (amber)</h3><canvas id="b_cum" height="100"></canvas></div>
    {'<div class="chart-box"><h3>Regime Gate (green)</h3><canvas id="r_cum" height="100"></canvas></div>' if r_raw else ''}
  </div>
</div>

<div class="section">
  <h2>Comparison</h2>
  <div class="tbl"><table>
    <thead><tr><th>Metric</th><th>Baseline</th>{cmp_regime}<th>SPY</th></tr></thead>
    <tbody>{cmp_rows}</tbody>
  </table></div>
</div>

<div class="section">
  <h2>Best Days — Baseline</h2>
  <div class="tbl"><table>
    <thead><tr><th>Date</th><th>Tickers</th><th>P&L</th></tr></thead>
    <tbody>{bw_rows(b_raw.get("best_days",[]))}</tbody>
  </table></div>
</div>

<div class="section">
  <h2>Worst Days — Baseline</h2>
  <div class="tbl"><table>
    <thead><tr><th>Date</th><th>Tickers</th><th>P&L</th></tr></thead>
    <tbody>{bw_rows(b_raw.get("worst_days",[]))}</tbody>
  </table></div>
</div>

<div class="section">
  <h2>Trade Book (first 100)</h2>
  <div class="tbl"><table>
    <thead><tr><th>Date</th><th>Ticker</th><th>VST</th><th>Entry</th><th>Exit</th><th>Ret%</th><th>P&L</th></tr></thead>
    <tbody>{trade_rows(b_raw)}</tbody>
  </table></div>
</div>

<script>{chart_js}</script>
</body></html>"""

    out = os.path.join(DATA_DIR, "stockscout3_report.html")
    open(out,"w").write(html)
    print(f"Report saved: {out}")

if __name__ == "__main__":
    build()
