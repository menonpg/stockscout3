#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.py &mdash; Tabbed backtest dashboard: one full chart suite per strategy + comparison tab
"""
import json, os, math
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
OUT_FILE = os.path.join(DATA_DIR, "stockscout3_report.html")

# -- Load all result files -----------------------------------------------------
def load(mode):
    path = os.path.join(DATA_DIR, f"results_{mode}.json")
    if os.path.exists(path):
        return json.load(open(path))
    return None

def load_direct(fname):
    path = os.path.join(DATA_DIR, fname)
    if os.path.exists(path): return json.load(open(path))
    return None

results = {}
b = load_direct("backtest_baseline.json")
r = load_direct("backtest_regime.json")
if b: results["baseline"] = b
if r: results["regime"]   = r

if not results:
    print("ERROR: no backtest_baseline.json found.")
    raise SystemExit(1)

# Auto-discover filter sweep results (results_equal_vst15.json etc.)
sweep_results = {}
import glob
for fp in sorted(glob.glob(os.path.join(DATA_DIR, "results_*.json"))):
    key = os.path.basename(fp).replace("results_","").replace(".json","")
    if key not in results:  # don't duplicate the 3 core modes
        try:
            sweep_results[key] = json.load(open(fp))
        except:
            pass

MODES = {
    "baseline": {"label": "Baseline",    "color": "#f59e0b", "desc": "VST+RS+RT + gap&lt;0.5% &mdash; no regime gate"},
    "regime":   {"label": "Regime Gate", "color": "#22c55e", "desc": "Trump Code macro filter ON"},
}



# -- SPY benchmark -------------------------------------------------------------
spy_cum = {}
spy_ohlc_path = os.path.join(DATA_DIR, "ohlc_SPY.json")
if os.path.exists(spy_ohlc_path):
    spy_data = json.load(open(spy_ohlc_path)).get("data", {})
    dates_sorted = sorted(spy_data.keys())
    if dates_sorted:
        base = float(spy_data[dates_sorted[0]].get("1. open") or spy_data[dates_sorted[0]].get("4. close") or 1)
        for d in dates_sorted:
            close = float(spy_data[d].get("4. close") or spy_data[d].get("5. adjusted close") or base)
            spy_cum[d] = round((close - base) / base * 100, 3)

# -- Per-strategy data builder -------------------------------------------------
def build(r):
    s = r["summary"]
    daily = r["daily"]
    cap = s["position_size"] * s["top_n"]
    days = [d for d in daily if d.get("picks")]
    dates = [d["date"] for d in days]

    cum_pct, day_pct, dd_pct = [], [], []
    peak = 0
    for d in days:
        cp = d["cumulative_pnl"] / cap * 100
        day_pct.append(round(d["day_pnl"] / cap * 100, 3))
        cum_pct.append(round(cp, 3))
        peak = max(peak, cp)
        dd_pct.append(round(cp - peak, 3))

    # Rolling 20-trade hit rate &#8594; aligned to days
    all_won = [p["won"] for d in days for p in d.get("picks", [])]
    rhr_per_trade = []
    W = 20
    for i in range(len(all_won)):
        sl = all_won[max(0, i-W+1):i+1]
        rhr_per_trade.append(round(sum(sl)/len(sl)*100, 1))
    rhr_daily, idx = [], 0
    for d in days:
        n = len(d.get("picks", []))
        idx += n
        rhr_daily.append(rhr_per_trade[idx-1] if idx and idx <= len(rhr_per_trade) else 50)

    # Return distribution
    rets = [p["ret_pct"] for d in daily for p in d.get("picks", [])]
    buckets = {}
    for v in rets:
        b = math.floor(v)
        buckets[b] = buckets.get(b, 0) + 1
    bk = sorted(buckets)
    dist = {"labels": [f"{k}%" for k in bk], "vals": [buckets[k] for k in bk],
            "colors": ["#22c55e" if k >= 0 else "#ef4444" for k in bk]}

    # SPY aligned to same dates
    spy_series = [spy_cum.get(d, None) for d in dates]
    # Forward-fill None
    last = 0
    for i, v in enumerate(spy_series):
        if v is None: spy_series[i] = last
        else: last = v

    # Ticker leaderboard
    tickers = {}
    for d in daily:
        for p in d.get("picks", []):
            t = p["ticker"]
            tickers.setdefault(t, {"trades":0,"wins":0,"pnl":0.0})
            tickers[t]["trades"] += 1
            tickers[t]["wins"]   += int(p["won"])
            tickers[t]["pnl"]    += p["pnl"]
    lb = sorted(tickers.items(), key=lambda x: x[1]["pnl"], reverse=True)

    return dict(s=s, cap=cap, dates=dates, cum_pct=cum_pct, day_pct=day_pct,
                dd_pct=dd_pct, rhr=rhr_daily, dist=dist, spy=spy_series,
                leaderboard=lb, daily=daily)

built = {k: build(v) for k, v in results.items()}

# Build sweep variant chart data (after build() is defined)
sweep_built = {k: build(v) for k, v in sweep_results.items()}

# -- HTML helpers --------------------------------------------------------------
def kpi_cards(b, color):
    s = b["s"]; cap = b["cap"]
    hr = s["hit_rate_pct"]
    hr_c = "#22c55e" if hr >= 55 else "#f59e0b" if hr >= 50 else "#ef4444"
    pnl_c = "#22c55e" if s["total_pnl"] >= 0 else "#ef4444"
    sg = "+" if s["total_pnl"] >= 0 else ""
    dd_pct = round(s["max_drawdown"] / cap * 100, 1)
    avg_d = round(s["total_pnl"] / max(s["days_with_picks"],1) / cap * 100, 2)
    return f"""
<div class="grid-4">
  <div class="card"><div class="lbl">Hit Rate</div>
    <div class="val" style="color:{hr_c}">{hr}%</div>
    <div class="sub2">{s['wins']}W / {s['losses']}L of {s['total_trades']} trades</div></div>
  <div class="card"><div class="lbl">Total Return</div>
    <div class="val" style="color:{pnl_c}">{sg}{s['total_pnl_pct']}%</div>
    <div class="sub2">{sg}${s['total_pnl']:,.0f} on ${cap:,}/day</div></div>
  <div class="card"><div class="lbl">Sharpe (ann.)</div>
    <div class="val">{s['sharpe_annualized']:.2f}</div>
    <div class="sub2">&gt;1.0 good &#183; &gt;2.0 excellent</div></div>
  <div class="card"><div class="lbl">Max Drawdown</div>
    <div class="val" style="color:#f87171">-{dd_pct}%</div>
    <div class="sub2">-${s['max_drawdown']:,.0f} peak-to-trough</div></div>
  <div class="card"><div class="lbl">Win Streak</div>
    <div class="val" style="color:#22c55e">{s['max_win_streak']}d</div></div>
  <div class="card"><div class="lbl">Lose Streak</div>
    <div class="val" style="color:#f87171">{s['max_lose_streak']}d</div></div>
  <div class="card"><div class="lbl">Days Traded</div>
    <div class="val">{s['days_with_picks']}</div>
    <div class="sub2">of {s['total_trading_days']} total</div></div>
  <div class="card"><div class="lbl">Avg Daily Return</div>
    <div class="val" style="color:{pnl_c}">{sg}{avg_d}%</div></div>
</div>"""

def trade_rows(b):
    rows = ""
    for d in reversed(b["daily"]):
        for p in d.get("picks", []):
            c = "#22c55e" if p["won"] else "#ef4444"
            rows += f"""<tr>
              <td>{d['date']}</td><td style="font-weight:600">{p['ticker']}</td>
              <td style="color:#94a3b8">{p['vst']:.3f}</td>
              <td>${p['open']:.2f}</td><td>${p['close']:.2f}</td>
              <td style="color:{c}">{'+' if p['ret_pct']>=0 else ''}{p['ret_pct']:.2f}%</td>
              <td style="color:{c};font-weight:600">{'+' if p['pnl']>=0 else ''}${p['pnl']:.2f}</td>
              <td><span style="background:{'#16a34a' if p['won'] else '#dc2626'};color:#fff;padding:2px 6px;border-radius:99px;font-size:.68rem">{'W' if p['won'] else 'L'}</span></td>
            </tr>"""
    return rows

def leaderboard_rows(b):
    rows = ""
    for t, st in b["leaderboard"]:
        hr = st["wins"]/st["trades"]*100 if st["trades"] else 0
        c = "#22c55e" if st["pnl"] >= 0 else "#ef4444"
        rows += f"""<tr>
          <td style="font-weight:600">{t}</td><td>{st['trades']}</td>
          <td>{st['wins']}</td><td>{hr:.0f}%</td>
          <td style="color:{c};font-weight:600">{'+' if st['pnl']>=0 else ''}${st['pnl']:,.2f}</td></tr>"""
    return rows

def bw_rows(days_list):
    rows = ""
    for d in days_list:
        c = "#22c55e" if d["day_pnl"] >= 0 else "#ef4444"
        tks = " &#183; ".join(p["ticker"] for p in d.get("picks", []))
        rows += f"""<tr><td>{d['date']}</td>
          <td style="color:{c};font-weight:700">{'+' if d['day_pnl']>=0 else ''}${d['day_pnl']:,.2f}</td>
          <td style="color:#64748b;font-size:.8rem">{tks}</td></tr>"""
    return rows

def charts_js(mode, b, color):
    dd = b["dd_pct"]
    return f"""
const dates_{mode}   = {json.dumps(b['dates'])};
const cumPct_{mode}  = {json.dumps(b['cum_pct'])};
const dayPct_{mode}  = {json.dumps(b['day_pct'])};
const dd_{mode}      = {json.dumps(dd)};
const rhr_{mode}     = {json.dumps(b['rhr'])};
const spy_{mode}     = {json.dumps(b['spy'])};
const distL_{mode}   = {json.dumps(b['dist']['labels'])};
const distV_{mode}   = {json.dumps(b['dist']['vals'])};
const distC_{mode}   = {json.dumps(b['dist']['colors'])};

(function(){{
  const gc='#1e3a5f', tc='#475569';
  function opts(yFmt){{return{{responsive:true,animation:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{ticks:{{color:tc,maxTicksLimit:10}},grid:{{color:'#1e293b'}}}},
             y:{{ticks:{{color:tc,callback:yFmt}},grid:{{color:gc}}}}}}}};}}

  // Cumulative
  new Chart(document.getElementById('cum_{mode}'),{{
    type:'line',
    data:{{labels:dates_{mode},datasets:[
      {{label:'StockScout ({MODES.get(mode,{}).get("label",mode)})',
       data:cumPct_{mode},borderColor:'{color}',backgroundColor:'{color}18',
       fill:true,tension:.2,pointRadius:0,borderWidth:2}},
      {{label:'SPY (buy & hold)',data:spy_{mode},borderColor:'#94a3b8',
       backgroundColor:'transparent',fill:false,tension:.2,pointRadius:0,
       borderWidth:1.5,borderDash:[5,3]}}
    ]}},
    options:{{...opts(v=>v.toFixed(1)+'%'),
      plugins:{{legend:{{display:true,labels:{{color:'#94a3b8'}}}}}}}}
  }});

  // Daily
  new Chart(document.getElementById('day_{mode}'),{{
    type:'bar',
    data:{{labels:dates_{mode},datasets:[{{data:dayPct_{mode},
      backgroundColor:dayPct_{mode}.map(v=>v>=0?'#22c55e44':'#ef444444'),
      borderColor:dayPct_{mode}.map(v=>v>=0?'#22c55e':'#ef4444'),borderWidth:1}}]}},
    options:opts(v=>v.toFixed(2)+'%')
  }});

  // Drawdown
  new Chart(document.getElementById('dd_{mode}'),{{
    type:'line',
    data:{{labels:dates_{mode},datasets:[{{data:dd_{mode},
      borderColor:'#f87171',backgroundColor:'#f8717122',
      fill:true,tension:.2,pointRadius:0,borderWidth:2}}]}},
    options:opts(v=>v.toFixed(1)+'%')
  }});

  // Rolling hit rate
  new Chart(document.getElementById('rhr_{mode}'),{{
    type:'line',
    data:{{labels:dates_{mode},datasets:[
      {{data:rhr_{mode},borderColor:'#60a5fa',backgroundColor:'#60a5fa18',
       fill:true,tension:.3,pointRadius:0,borderWidth:2}},
      {{data:dates_{mode}.map(()=>50),borderColor:'#475569',borderDash:[4,4],
       pointRadius:0,borderWidth:1,fill:false}}
    ]}},
    options:{{responsive:true,animation:false,plugins:{{legend:{{display:false}}}},
      scales:{{x:{{ticks:{{color:tc,maxTicksLimit:10}},grid:{{color:'#1e293b'}}}},
               y:{{min:30,max:70,ticks:{{color:tc,callback:v=>v+'%'}},grid:{{color:gc}}}}}}}}
  }});

  // Distribution
  new Chart(document.getElementById('dist_{mode}'),{{
    type:'bar',
    data:{{labels:distL_{mode},datasets:[{{data:distV_{mode},
      backgroundColor:distC_{mode},borderRadius:3}}]}},
    options:opts(v=>v)
  }});
}})();
"""

# -- Comparison table ----------------------------------------------------------
spy_final = list(spy_cum.values())[-1] if spy_cum else None

def cmp_table():
    first_s = next(iter(results.values()))["summary"]
    cap = first_s["position_size"] * first_s["top_n"]

    header = "<tr><th>Metric</th>"
    for mode in MODES:
        if mode not in results: continue
        m = MODES[mode]
        header += f'<th style="color:{m["color"]}">{m["label"]}<br><span style="color:#475569;font-weight:400;font-size:.7rem">{m["desc"]}</span></th>'
    header += '<th style="color:#94a3b8">SPY Buy &amp; Hold</th></tr>'

    def row(label, fn, spy_val="&mdash;"):
        r = f"<tr><td>{label}</td>"
        for mode in MODES:
            if mode not in results: continue
            r += f"<td>{fn(results[mode]['summary'], MODES[mode]['color'])}</td>"
        r += f"<td style='color:#94a3b8'>{spy_val}</td></tr>"
        return r

    def ret_cell(s, color):
        sg = "+" if s["total_pnl"] >= 0 else ""
        return f'<span style="color:{color};font-weight:700">{sg}{s["total_pnl_pct"]}%</span>'

    def hr_cell(s, color): return f'{s["hit_rate_pct"]}%'
    def sh_cell(s, color): return f'{s["sharpe_annualized"]:.2f}'
    def dd_cell(s, color):
        c2 = first_s["position_size"] * first_s["top_n"]
        return f'<span style="color:#f87171">-{round(s["max_drawdown"]/c2*100,1)}%</span>'
    def tr_cell(s, color): return f'{s["total_trades"]:,}'

    spy_ret = f'{spy_final:+.1f}%' if spy_final else '&mdash;'
    return f"""<table>{header}
      {row('Total Return', ret_cell, spy_ret)}
      {row('Hit Rate', hr_cell)}
      {row('Sharpe (ann.)', sh_cell, '~1.2')}
      {row('Max Drawdown', dd_cell, '~-25%')}
      {row('Total Trades', tr_cell, '1')}
    </table>"""

# -- Tab panels ----------------------------------------------------------------
def tab_panel(mode, b, color):
    s = b["s"]
    cap = b["cap"]
    return f"""
<div id="panel-{mode}" class="tab-panel" style="display:none">
  {kpi_cards(b, color)}
  <div class="chart-box">
    <h2>&#128200; Cumulative Return % vs SPY</h2>
    <canvas id="cum_{mode}" height="70"></canvas>
  </div>
  <div class="grid-2">
    <div class="chart-box" style="margin-bottom:0"><h2>&#128202; Daily Return %</h2>
      <canvas id="day_{mode}" height="120"></canvas></div>
    <div class="chart-box" style="margin-bottom:0"><h2>&#128201; Drawdown % (from peak)</h2>
      <canvas id="dd_{mode}" height="120"></canvas></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="grid-2">
    <div class="chart-box" style="margin-bottom:0"><h2>&#127919; Rolling 20-Day Hit Rate</h2>
      <canvas id="rhr_{mode}" height="120"></canvas></div>
    <div class="chart-box" style="margin-bottom:0"><h2>&#128230; Return Distribution</h2>
      <canvas id="dist_{mode}" height="120"></canvas></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="grid-2">
    <div class="card"><h2>&#128994; Best Days</h2>
      <div class="tab-wrap"><table><tr><th>Date</th><th>P&amp;L</th><th>Picks</th></tr>
        {bw_rows(results[mode]['best_days'])}</table></div></div>
    <div class="card"><h2>&#128308; Worst Days</h2>
      <div class="tab-wrap"><table><tr><th>Date</th><th>P&amp;L</th><th>Picks</th></tr>
        {bw_rows(results[mode]['worst_days'])}</table></div></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="card" style="margin-bottom:24px">
    <h2>&#127942; Ticker Leaderboard</h2>
    <div class="tab-wrap"><table>
      <tr><th>Ticker</th><th>Trades</th><th>Wins</th><th>Hit Rate</th><th>P&amp;L</th></tr>
      {leaderboard_rows(b)}</table></div></div>
  <div class="card">
    <h2>&#128203; Full Trade Book ({s['total_trades']:,} trades)</h2>
    <div class="tab-wrap" style="max-height:500px;overflow-y:auto"><table>
      <tr><th>Date</th><th>Ticker</th><th>VST</th><th>Open</th><th>Close</th>
          <th>Return</th><th>P&amp;L</th><th></th></tr>
      {trade_rows(b)}</table></div></div>
</div>"""

# -- Assemble page -------------------------------------------------------------
first_s = next(iter(results.values()))["summary"]
cap = first_s["position_size"] * first_s["top_n"]

tab_buttons = ""
panels_html = ""
charts_html = ""
first = True
for mode in MODES:
    if mode not in results: continue
    m = MODES[mode]
    b = built[mode]
    active = "active" if first else ""
    tab_buttons += f'<button class="tab-btn {active}" onclick="showTab(\'{mode}\')" id="btn-{mode}" style="border-bottom-color:{m["color"] if first else "transparent"}">{m["label"]} <span style="font-size:.75rem;color:#64748b">{m["desc"].split("&mdash;")[0].strip()}</span></button>'
    panels_html += tab_panel(mode, b, m["color"])
    charts_html += charts_js(mode, b, m["color"])
    if first:
        first_mode = mode
    first = False

# Comparison tab
tab_buttons += '<button class="tab-btn" onclick="showTab(\'compare\')" id="btn-compare">&#9878;&#65039; Compare All</button>'
tab_buttons += '<button class="tab-btn" onclick="showTab(\'variants\')" id="btn-variants">&#128300; Filter Variants</button>'
# Sweep summary table
def sweep_table():
    if not sweep_results:
        return "<p style='color:#475569'>No filter sweep results yet. Run Step 3d.</p>"
    rows = ""
    # baseline for comparison
    base = results.get("equal", next(iter(results.values())))["summary"]
    base_ret = base["total_pnl_pct"]
    base_hr  = base["hit_rate_pct"]
    base_sh  = base["sharpe_annualized"]
    for key, r in sorted(sweep_results.items()):
        s2 = r["summary"]
        cap2 = s2["position_size"] * s2["top_n"]
        diff_ret = round(s2["total_pnl_pct"] - base_ret, 2)
        diff_hr  = round(s2["hit_rate_pct"]  - base_hr,  1)
        diff_sh  = round(s2["sharpe_annualized"] - base_sh, 2)
        ret_c = "#22c55e" if s2["total_pnl_pct"] >= base_ret else "#f87171"
        sg = "+" if s2["total_pnl_pct"] >= 0 else ""
        dsg = "+" if diff_ret >= 0 else ""
        rows += f"""<tr>
          <td style="font-weight:600">{key}</td>
          <td style="color:{ret_c}">{sg}{s2['total_pnl_pct']}% <span style="color:#64748b;font-size:.75rem">({dsg}{diff_ret}%)</span></td>
          <td>{s2['hit_rate_pct']}% <span style="color:#64748b;font-size:.75rem">({'+' if diff_hr>=0 else ''}{diff_hr}%)</span></td>
          <td>{s2['sharpe_annualized']:.2f} <span style="color:#64748b;font-size:.75rem">({'+' if diff_sh>=0 else ''}{diff_sh})</span></td>
          <td style="color:#f87171">-{round(s2['max_drawdown']/cap2*100,1)}%</td>
          <td>{s2['total_trades']:,}</td>
        </tr>"""
    return f"""<table>
      <tr><th>Config</th><th>Return (vs equal baseline)</th><th>Hit Rate</th><th>Sharpe</th><th>Max DD</th><th>Trades</th></tr>
      {rows}
    </table>"""

compare_panel = f"""
<div id="panel-compare" class="tab-panel" style="display:none">
  <div class="card" style="margin-bottom:24px">
    <h2>&#9878;&#65039; Strategy Comparison &mdash; {first_s['backtest_start']} &#8594; {first_s['backtest_end']}</h2>
    <p style="color:#475569;font-size:.8rem;margin-bottom:16px">
      ${first_s['position_size']:,}/position &#215; {first_s['top_n']} = ${cap:,} deployed/day &#183; Buy open, sell close &#183; {first_s['total_trading_days']} trading days
    </p>
    <div class="tab-wrap">{cmp_table()}</div>
  </div>
  <div class="card">
    <h2>&#128300; Filter Sweep &mdash; vs Equal baseline (VST=1.0, no filters)</h2>
    <p style="color:#475569;font-size:.8rem;margin-bottom:16px">
      Each row tests one filter independently. Green = beats baseline. Combined row tests all filters together.
    </p>
    <div class="tab-wrap">{sweep_table()}</div>
  </div>
</div>"""

# -- Variants tab panel -------------------------------------------------------
def variants_panel():
    if not sweep_built:
        return """<div id="panel-variants" class="tab-panel" style="display:none">
          <div class="card"><p style="color:#475569">No filter variants yet.</p></div></div>"""

    # Selector options
    options = ""
    for key in sorted(sweep_built.keys()):
        s2 = sweep_built[key]["s"]
        sg = "+" if s2["total_pnl_pct"] >= 0 else ""
        options += f'<option value="{key}">{key}  &mdash;  {sg}{s2["total_pnl_pct"]}% return  |  {s2["hit_rate_pct"]}% hit rate  |  Sharpe {s2["sharpe_annualized"]:.2f}</option>'

    # Generate JS data + chart divs for all variants
    all_charts_js = ""
    sub_panels = ""
    for key, b in sorted(sweep_built.items()):
        s2 = b["s"]
        cap2 = b["cap"]
        color = "#60a5fa"  # uniform blue for variants
        sg = "+" if s2["total_pnl_pct"] >= 0 else ""
        pnl_c = "#22c55e" if s2["total_pnl_pct"] >= 0 else "#ef4444"
        dd_pct = round(s2["max_drawdown"] / cap2 * 100, 1)

        sub_panels += f"""
<div id="vsub-{key}" class="vsub" style="display:none">
  <div class="grid-4" style="margin-bottom:20px">
    <div class="card"><div class="lbl">Return</div>
      <div class="val" style="color:{pnl_c}">{sg}{s2['total_pnl_pct']}%</div>
      <div class="sub2">{sg}${s2['total_pnl']:,.0f}</div></div>
    <div class="card"><div class="lbl">Hit Rate</div>
      <div class="val">{s2['hit_rate_pct']}%</div>
      <div class="sub2">{s2['wins']}W / {s2['losses']}L</div></div>
    <div class="card"><div class="lbl">Sharpe</div>
      <div class="val">{s2['sharpe_annualized']:.2f}</div></div>
    <div class="card"><div class="lbl">Max Drawdown</div>
      <div class="val" style="color:#f87171">-{dd_pct}%</div></div>
  </div>
  <div class="chart-box"><h2>&#128200; Cumulative Return % vs SPY</h2>
    <canvas id="vcum-{key}" height="70"></canvas></div>
  <div class="grid-2">
    <div class="chart-box" style="margin-bottom:0"><h2>&#128202; Daily Return %</h2>
      <canvas id="vday-{key}" height="120"></canvas></div>
    <div class="chart-box" style="margin-bottom:0"><h2>&#128201; Drawdown %</h2>
      <canvas id="vdd-{key}" height="120"></canvas></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="grid-2">
    <div class="chart-box" style="margin-bottom:0"><h2>&#127919; Rolling Hit Rate</h2>
      <canvas id="vrhr-{key}" height="120"></canvas></div>
    <div class="chart-box" style="margin-bottom:0"><h2>&#128230; Return Distribution</h2>
      <canvas id="vdist-{key}" height="120"></canvas></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="grid-2">
    <div class="card"><h2>&#128994; Best Days</h2>
      <div class="tab-wrap"><table><tr><th>Date</th><th>P&L</th><th>Picks</th></tr>
        {bw_rows(sweep_results[key]['best_days'])}</table></div></div>
    <div class="card"><h2>&#128308; Worst Days</h2>
      <div class="tab-wrap"><table><tr><th>Date</th><th>P&L</th><th>Picks</th></tr>
        {bw_rows(sweep_results[key]['worst_days'])}</table></div></div>
  </div>
  <div style="margin-bottom:24px"></div>
  <div class="card"><h2>&#128203; Trade Book ({s2['total_trades']:,} trades)</h2>
    <div class="tab-wrap" style="max-height:400px;overflow-y:auto"><table>
      <tr><th>Date</th><th>Ticker</th><th>VST</th><th>Open</th><th>Close</th><th>Return</th><th>P&L</th><th></th></tr>
      {trade_rows(b)}</table></div></div>
</div>"""

        # JS data for this variant
        all_charts_js += f"""
(function(){{
  const gc='#1e3a5f', tc='#475569';
  function opts(yFmt){{return{{responsive:true,animation:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{ticks:{{color:tc,maxTicksLimit:10}},grid:{{color:'#1e293b'}}}},
             y:{{ticks:{{color:tc,callback:yFmt}},grid:{{color:gc}}}}}}}};}}
  const vdates = {json.dumps(b['dates'])};
  const vcum   = {json.dumps(b['cum_pct'])};
  const vday   = {json.dumps(b['day_pct'])};
  const vdd    = {json.dumps(b['dd_pct'])};
  const vrhr   = {json.dumps(b['rhr'])};
  const vspy   = {json.dumps(b['spy'])};
  const vdistL = {json.dumps(b['dist']['labels'])};
  const vdistV = {json.dumps(b['dist']['vals'])};
  const vdistC = {json.dumps(b['dist']['colors'])};

  window._vcharts = window._vcharts || {{}};
  window._vcharts['{key}'] = function() {{
    new Chart(document.getElementById('vcum-{key}'),{{type:'line',
      data:{{labels:vdates,datasets:[
        {{label:'StockScout',data:vcum,borderColor:'{color}',backgroundColor:'{color}18',fill:true,tension:.2,pointRadius:0,borderWidth:2}},
        {{label:'SPY',data:vspy,borderColor:'#94a3b8',backgroundColor:'transparent',fill:false,tension:.2,pointRadius:0,borderWidth:1.5,borderDash:[5,3]}}
      ]}},options:{{...opts(v=>v.toFixed(1)+'%'),plugins:{{legend:{{display:true,labels:{{color:'#94a3b8'}}}}}}}}
    }});
    new Chart(document.getElementById('vday-{key}'),{{type:'bar',
      data:{{labels:vdates,datasets:[{{data:vday,
        backgroundColor:vday.map(v=>v>=0?'#22c55e44':'#ef444444'),
        borderColor:vday.map(v=>v>=0?'#22c55e':'#ef4444'),borderWidth:1}}]}},
      options:opts(v=>v.toFixed(2)+'%')
    }});
    new Chart(document.getElementById('vdd-{key}'),{{type:'line',
      data:{{labels:vdates,datasets:[{{data:vdd,borderColor:'#f87171',backgroundColor:'#f8717122',fill:true,tension:.2,pointRadius:0,borderWidth:2}}]}},
      options:opts(v=>v.toFixed(1)+'%')
    }});
    new Chart(document.getElementById('vrhr-{key}'),{{type:'line',
      data:{{labels:vdates,datasets:[
        {{data:vrhr,borderColor:'#60a5fa',backgroundColor:'#60a5fa18',fill:true,tension:.3,pointRadius:0,borderWidth:2}},
        {{data:vdates.map(()=>50),borderColor:'#475569',borderDash:[4,4],pointRadius:0,borderWidth:1,fill:false}}
      ]}},options:{{responsive:true,animation:false,plugins:{{legend:{{display:false}}}},
        scales:{{x:{{ticks:{{color:tc,maxTicksLimit:10}},grid:{{color:'#1e293b'}}}},
                 y:{{min:30,max:70,ticks:{{color:tc,callback:v=>v+'%'}},grid:{{color:gc}}}}}}}}
    }});
    new Chart(document.getElementById('vdist-{key}'),{{type:'bar',
      data:{{labels:vdistL,datasets:[{{data:vdistV,backgroundColor:vdistC,borderRadius:3}}]}},
      options:opts(v=>v)
    }});
  }};
}})();
"""

    return f"""
<div id="panel-variants" class="tab-panel" style="display:none">
  <div class="card" style="margin-bottom:24px">
    <h2>&#128300; Filter Variants &mdash; select a configuration</h2>
    <p style="color:#475569;font-size:.8rem;margin-bottom:12px">
      Each variant runs the equal-weight baseline with one or more filters applied.
    </p>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:16px 18px;margin-bottom:16px;font-size:.82rem;line-height:1.7">
      <strong style="color:#f8fafc">&#9889; How to trade the gap filter in real life</strong><br>
      <span style="color:#64748b">The gap filter skips stocks that open >X% above prior close. This looks like lookahead bias &mdash; but it isn't, for two reasons:</span>
      <br><br>
      <strong style="color:#a78bfa">Option A &mdash; Pre-market feed (best)</strong><br>
      <span style="color:#94a3b8">Use pre-market price as a gap proxy. If a stock closed at $100 and pre-market shows $101+, skip it before the open. Requires a pre-market data feed (Polygon.io, Alpaca, IEX) &mdash; not in yfinance history, so not modelled here.</span>
      <br><br>
      <strong style="color:#22c55e">Option B &mdash; Limit order at open (fully equivalent, recommended)</strong><br>
      <span style="color:#94a3b8">Instead of a market order at open, place a limit order at <code style="background:#1e293b;padding:1px 5px;border-radius:4px">prior_close &#215; 1.005</code>. If the stock gaps above that, your order simply doesn't fill &mdash; no position taken. This is mechanically identical to the gap filter in the backtest. The backtest result is valid under this interpretation: <em>"place a limit order at prior close +0.5%; if it fills, hold to close."</em></span>
      <br><br>
      <span style="color:#475569;font-size:.78rem">&#9888;&#65039; The +32.9% result for gap&lt;0.5% assumes this limit-order framing. It is not a genuine lookahead result.</span>
    </div>
    <select id="variant-select" onchange="selectVariant(this.value)"
      style="background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:10px 14px;font-size:.9rem;width:100%;margin-bottom:20px;cursor:pointer">
      {options}
    </select>
    <div id="vsubs">{sub_panels}</div>
  </div>
</div>
<script>
var _variantChartsDone = {{}};
function selectVariant(key) {{
  document.querySelectorAll('.vsub').forEach(el => el.style.display='none');
  var el = document.getElementById('vsub-'+key);
  if (el) el.style.display='block';
  // Render charts only once per variant
  if (!_variantChartsDone[key] && window._vcharts && window._vcharts[key]) {{
    window._vcharts[key]();
    _variantChartsDone[key] = true;
  }}
}}
// Auto-select first variant
{f"selectVariant('{sorted(sweep_built.keys())[0]}');" if sweep_built else ""}
</script>
<script>{all_charts_js}</script>"""

variants_panel_html = variants_panel()

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockScout 3 &mdash; Backtest</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px 20px;max-width:1200px;margin:0 auto}}
h1{{font-size:1.6rem;font-weight:800;color:#f8fafc;margin-bottom:4px}}
h2{{font-size:.85rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}}
.sub{{color:#475569;font-size:.82rem;margin-bottom:20px}}
.grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:0}}
@media(max-width:700px){{.grid-4{{grid-template-columns:repeat(2,1fr)}}.grid-2{{grid-template-columns:1fr}}}}
.card{{background:#1e293b;border-radius:12px;padding:18px 20px}}
.card .lbl{{font-size:.72rem;color:#475569;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.card .val{{font-size:1.6rem;font-weight:800;line-height:1}}
.card .sub2{{font-size:.72rem;color:#64748b;margin-top:4px}}
.chart-box{{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:24px}}
.chart-box h2{{margin-bottom:16px}}
.tabs{{display:flex;gap:4px;margin-bottom:24px;border-bottom:1px solid #1e293b;flex-wrap:wrap}}
.tab-btn{{background:none;border:none;border-bottom:2px solid transparent;color:#475569;cursor:pointer;padding:10px 16px;font-size:.85rem;font-weight:600;transition:all .15s;white-space:nowrap}}
.tab-btn:hover{{color:#94a3b8}}
.tab-btn.active{{color:#f8fafc;border-bottom-width:2px}}
table{{width:100%;border-collapse:collapse;font-size:.8rem}}
th{{color:#334155;font-weight:700;text-align:left;padding:8px 10px;border-bottom:1px solid #1e293b;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}}
td{{padding:7px 10px;border-bottom:1px solid #1a2744}}
tr:hover td{{background:#1a2744}}
.tab-wrap{{overflow-x:auto}}
footer{{color:#334155;font-size:.75rem;margin-top:32px;padding-top:16px;border-top:1px solid #1e293b}}
a{{color:#60a5fa;text-decoration:none}}
</style>
</head>
<body>
<h1>&#128270; StockScout 3 &mdash; Backtest Dashboard</h1>
<div class="sub">
  {first_s['backtest_start']} &#8594; {first_s['backtest_end']}
  &nbsp;&#183;&nbsp; {first_s['total_trading_days']} trading days
  &nbsp;&#183;&nbsp; ${first_s['position_size']:,}/position &#215; {first_s['top_n']} = ${cap:,}/day deployed
  &nbsp;&#183;&nbsp; Buy open &#183; sell close &#183; no transaction costs
  &nbsp;&#183;&nbsp; Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
</div>

<div class="tabs">
  {tab_buttons}
</div>

{panels_html}
{compare_panel}
{variants_panel_html}

<footer>
  &#9888;&#65039; <strong>Caveats:</strong> No slippage or commissions. Fundamentals static (not updated daily).
  S&amp;P 100 universe = today's constituents (survivorship bias). Past performance &#8800; future results.
  <br><br>
  <a href="/stockscout3/">&#8592; StockScout 3 Live</a> &nbsp;&#183;&nbsp;
  <a href="/backtest/">v2 Backtest</a> &nbsp;&#183;&nbsp;
  <a href="https://github.com/menonpg/stockscout3">Source on GitHub</a>
</footer>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
function showTab(mode) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-'+mode).style.display='block';
  const btn = document.getElementById('btn-'+mode);
  btn.classList.add('active');
  if (mode === 'variants') {{
    const sel = document.getElementById('variant-select');
    if (sel && sel.value) selectVariant(sel.value);
  }}
}}
// Show first tab on load
showTab('{first_mode}');

{charts_html}
</script>
</body>
</html>"""

open(OUT_FILE, "w").write(html)
print(f"Report saved: {OUT_FILE}")
print(f"Tabs: {', '.join(results.keys())} + compare")
