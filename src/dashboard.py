"""
Local monitoring dashboard for the VIX>40 "buy the fear" TQQQ strategy.

Run:
    python src/dashboard.py
then open http://localhost:8000   (set PORT=... to change; macOS uses 5000 for AirPlay)

Serves a modern, interactive page (Plotly): TQQQ price + the two trigger
indicators (VIX, S&P weekly RSI), all mouse-zoomable with 3M/6M/1Y/3Y/Max
range buttons, plus a strategy + live-status summary on top. Data is read
fresh on every request, so re-running the downloader updates the view.
"""

import os
import json

import numpy as np
import pandas as pd
from flask import Flask, render_template_string

import backtest as bt

app = Flask(__name__)


def _series(s):
    """Series -> list with NaN replaced by None (JSON-safe)."""
    return [None if pd.isna(v) else round(float(v), 4) for v in s]


def build_payload():
    df = bt.build_signals()
    tqqq = bt.load_yf(os.path.join(bt.DATA, "tqqq_data.csv")).reindex(df.index)
    trades, equity = bt.run_backtest(df)
    tqqq_bh = bt.buy_hold_equity(df["tqqq_close"])
    m = bt.metrics(equity, tqqq_bh.pct_change().dropna())

    last_date = df.index[-1]
    cur_price = float(df["tqqq_close"].iloc[-1])
    cur_vix = float(df["vix_close"].iloc[-1])
    cur_rsi = float(df["weekly_rsi"].iloc[-1])
    spx_last = float(df["spx_close"].iloc[-1])
    ma_last = float(df["ma100"].iloc[-1])

    last = trades.iloc[-1]
    in_pos = bool(last.get("Open_At_End") is True)

    if in_pos:
        entry_date = pd.Timestamp(last["Entry_Date"])
        entry_price = float(last["Entry_Price"])
        hold_days = int((last_date - entry_date).days)
        status = {
            "in_position": True,
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
            "current_price": round(cur_price, 2),
            "unrealized_pct": round((cur_price / entry_price - 1) * 100, 1),
            "hold_days": hold_days,
            "min_hold_left": max(0, 365 - hold_days),
            "exit_armed": hold_days >= 365,
            "below_ma100": spx_last < ma_last,
            "trigger": last["Trigger"],
        }
    else:
        status = {
            "in_position": False,
            "current_price": round(cur_price, 2),
            "signal_now": bool(df["signal"].iloc[-1]),
        }

    trade_list = []
    for _, t in trades.iterrows():
        trade_list.append({
            "signal_date": pd.Timestamp(t["Signal_Date"]).strftime("%Y-%m-%d"),
            "entry_date": pd.Timestamp(t["Entry_Date"]).strftime("%Y-%m-%d"),
            "entry_price": round(float(t["Entry_Price"]), 2),
            "exit_date": pd.Timestamp(t["Exit_Date"]).strftime("%Y-%m-%d"),
            "exit_price": round(float(t["Exit_Price"]), 2),
            "ret": round(float(t["Return_%"]), 1),
            "trigger": t["Trigger"],
            "open": bool(t.get("Open_At_End") is True),
        })

    trading = set(df.index)
    holidays = [d.strftime("%Y-%m-%d")
                for d in pd.bdate_range(df.index[0], df.index[-1]) if d not in trading]

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "holidays": holidays,
        "tqqq": _series(df["tqqq_close"]),
        "tqqq_open": _series(tqqq["Open"]),
        "tqqq_high": _series(tqqq["High"]),
        "tqqq_low": _series(tqqq["Low"]),
        "vix": _series(df["vix_close"]),
        "rsi": _series(df["weekly_rsi"]),
        "trades": trade_list,
        "status": status,
        "metrics": {
            "final_equity": round(m["Final Equity"]),
            "cagr": round(m["CAGR %"], 1),
            "max_dd": round(m["Max DD %"], 1),
            "sharpe": round(m["Sharpe"], 2),
            "n_trades": len(trades),
            "win_rate": round((trades["Return_%"] > 0).mean() * 100),
        },
        "current": {
            "date": last_date.strftime("%Y-%m-%d"),
            "vix": round(cur_vix, 1),
            "vix_hit": cur_vix > bt.VIX_THRESHOLD,
            "rsi": round(cur_rsi, 1),
            "rsi_hit": cur_rsi < bt.RSI_THRESHOLD,
        },
        "thresholds": {"vix": bt.VIX_THRESHOLD, "rsi": bt.RSI_THRESHOLD},
    }


@app.route("/")
def index():
    return render_template_string(PAGE, data=json.dumps(build_payload()))


PAGE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIX&gt;40 恐慌抄底 · 监控面板</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root{--bg:#0f1419;--card:#1a2029;--ink:#e6edf3;--muted:#9aa7b4;--line:#2d333b;
        --accent:#f0883e;--green:#3fb950;--red:#f85149;--blue:#58a6ff;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
  .wrap{max-width:1180px;margin:0 auto;padding:22px 18px 60px}
  h1{font-size:22px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:13.5px;margin-bottom:18px}
  .grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-bottom:11px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 15px}
  .card h3{margin:0 0 5px;font-size:11.5px;color:var(--muted);font-weight:600;letter-spacing:.4px;text-transform:uppercase}
  .big{font-size:26px;font-weight:800}
  .row{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--line);font-size:12.5px}
  .row:last-child{border-bottom:none}
  .row .k{color:var(--muted)}
  .pill{display:inline-block;padding:3px 12px;border-radius:20px;font-size:13px;font-weight:700}
  .pill.in{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.4)}
  .pill.flat{background:rgba(154,167,180,.12);color:var(--muted);border:1px solid var(--line)}
  .pos{color:var(--green)} .neg{color:var(--red)} .hot{color:var(--accent)} .accent{color:var(--accent)}
  .rules{font-size:12.5px;line-height:1.42;color:#cdd6e0}
  .rules b{color:var(--accent)}
  #chart{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px}
  .foot{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
</style>
</head>
<body>
<div class="wrap">
  <h1>VIX &gt; 40「恐慌抄底」· 监控面板</h1>
  <div class="sub" id="asof"></div>

  <div class="grid">
    <div class="card">
      <h3>策略规则</h3>
      <div class="rules">
        <div>📈 <b>信号</b>：VIX 收盘 &gt; 40 <b>或</b> 标普周线 RSI(14) &lt; 35</div>
        <div>🛒 <b>入场</b>：信号后第 9 个交易日收盘买入 TQQQ</div>
        <div>🚪 <b>出场</b>：至少持有 1 年，之后标普首次收盘跌破 MA100 即卖出</div>
        <div>💰 <b>仓位</b>：满仓复利，同一时间仅一笔</div>
      </div>
    </div>
    <div class="card" id="statusCard"><h3>当前状态 <span id="statusPill"></span></h3><div id="status"></div></div>
    <div class="card"><h3>当前读数</h3><div id="readings"></div></div>
  </div>

  <div id="chart" style="height:1560px"></div>
  <div class="foot">数据本地读取，刷新页面即更新 · Plotly 交互图：拖拽缩放、滚轮缩放、上方按钮切换区间</div>
</div>

<script>
const D = {{ data|safe }};

/* ---------- summary cards ---------- */
const cur = D.current, st = D.status;
document.getElementById('asof').textContent = '数据截至 ' + cur.date;

function fmtMoney(n){return '$'+n.toLocaleString('en-US');}

let statusHTML = '', pillHTML = '';
if (st.in_position){
  pillHTML = '<span class="pill in">持仓中</span>';
  const armed = st.exit_armed
    ? (st.below_ma100 ? '<span class="neg">已满足（标普&lt;MA100）→ 待卖出</span>' : '<span class="pos">已解锁，等待标普跌破 MA100</span>')
    : ('锁定中，还需 '+st.min_hold_left+' 天');
  statusHTML = `
    <div class="row"><span class="k">买入</span><span>${st.entry_date} · $${st.entry_price}</span></div>
    <div class="row"><span class="k">现价 / 浮动</span><span>$${st.current_price} · <span class="${st.unrealized_pct>=0?'pos':'neg'}">${st.unrealized_pct>=0?'+':''}${st.unrealized_pct}%</span></span></div>
    <div class="row"><span class="k">持有 / 出场</span><span>${st.hold_days} 天 · ${armed}</span></div>`;
} else {
  pillHTML = '<span class="pill flat">空仓</span>';
  statusHTML = `
    <div class="row"><span class="k">现价</span><span>$${st.current_price}</span></div>
    <div class="row"><span class="k">当前是否触发</span><span>${st.signal_now?'<span class="hot">是 · 准备入场</span>':'否，等待恐慌信号'}</span></div>`;
}
document.getElementById('status').innerHTML = statusHTML;
document.getElementById('statusPill').innerHTML = pillHTML;

document.getElementById('readings').innerHTML = `
  <div class="row"><span class="k">TQQQ</span><span>$${st.current_price}</span></div>
  <div class="row"><span class="k">VIX</span><span class="${cur.vix_hit?'hot':''}">${cur.vix} ${cur.vix_hit?'· &gt;40 ✔':''}</span></div>
  <div class="row"><span class="k">标普 RSI(14)</span><span class="${cur.rsi_hit?'hot':''}">${cur.rsi} ${cur.rsi_hit?'· &lt;35 ✔':''}</span></div>`;

/* ---------- charts ---------- */
const dates = D.dates;
const entryX=[], entryY=[], entryT=[], exitX=[], exitY=[], exitT=[];
D.trades.forEach(t=>{
  entryX.push(t.entry_date); entryY.push(t.entry_price);
  entryT.push(`买入 $${t.entry_price}<br>${t.trigger}`);
  if(!t.open){ exitX.push(t.exit_date); exitY.push(t.exit_price);
    exitT.push(`卖出 $${t.exit_price}<br>收益 ${t.ret>=0?'+':''}${t.ret}%`); }
});

const price = {x:dates,open:D.tqqq_open,high:D.tqqq_high,low:D.tqqq_low,close:D.tqqq,
  type:'candlestick',name:'TQQQ',xaxis:'x',yaxis:'y',
  increasing:{line:{color:'#3fb950'},fillcolor:'#3fb950'},
  decreasing:{line:{color:'#f85149'},fillcolor:'#f85149'}};
const entry = {x:entryX,y:entryY,type:'scatter',mode:'markers',name:'买入',
  marker:{color:'#3fb950',symbol:'triangle-up',size:13,line:{color:'#fff',width:1}},
  text:entryT,hovertemplate:'%{text}<extra></extra>',xaxis:'x',yaxis:'y'};
const exit = {x:exitX,y:exitY,type:'scatter',mode:'markers',name:'卖出',
  marker:{color:'#f85149',symbol:'triangle-down',size:13,line:{color:'#fff',width:1}},
  text:exitT,hovertemplate:'%{text}<extra></extra>',xaxis:'x',yaxis:'y'};
const vix = {x:dates,y:D.vix,type:'scatter',mode:'lines',name:'VIX',
  line:{color:'#f0883e',width:1},xaxis:'x',yaxis:'y2',hovertemplate:'%{x}<br>VIX %{y}<extra></extra>'};
const rsi = {x:dates,y:D.rsi,type:'scatter',mode:'lines',name:'标普 RSI(14)',
  line:{color:'#58a6ff',width:1},xaxis:'x',yaxis:'y3',hovertemplate:'%{x}<br>RSI %{y}<extra></extra>'};

/* arrowed textboxes marking signal / entry / exit on the trigger panels (VIX=y2, RSI=y3) */
const trigAnn=[];
function tbox(x,y,yref,txt,color,ax,ay){
  return {x:x,y:y,xref:'x',yref:yref,text:txt,
    showarrow:true,arrowhead:3,arrowsize:1,arrowwidth:1.2,arrowcolor:color,ax:ax,ay:ay,
    font:{size:11,color:'#fff'},bgcolor:color,bordercolor:'#0f1419',borderwidth:1,
    borderpad:3,opacity:0.96};
}
function markRow(x,idx,label,color,ax,ay,doVix,doRsi){
  if(idx<0) return;
  if(doVix && D.vix[idx]!=null) trigAnn.push(tbox(x,D.vix[idx],'y2',label,color,ax,ay));
  if(doRsi && D.rsi[idx]!=null) trigAnn.push(tbox(x,D.rsi[idx],'y3',label,color,ax,ay));
}
D.trades.forEach(t=>{
  const si=dates.indexOf(t.signal_date), ei=dates.indexOf(t.entry_date), xi=dates.indexOf(t.exit_date);
  const sigTxt='信号 '+t.signal_date, buyTxt='买入 '+t.entry_date,
        sellTxt='卖出 '+t.exit_date+'<br>买入 '+t.entry_date;

  /* trigger panels: only mark the panel(s) of the trigger that fired.
     fan signal/buy/sell out (center / right / left) so clustered events don't overlap. */
  const doVix=t.trigger.indexOf('VIX')>=0, doRsi=t.trigger.indexOf('RSI')>=0;
  markRow(t.signal_date, si, sigTxt, '#f0883e',   0, -64, doVix, doRsi);
  markRow(t.entry_date,  ei, buyTxt, '#3fb950',  62, -34, doVix, doRsi);
  if(!t.open) markRow(t.exit_date, xi, sellTxt, '#f85149', -64, -52, doVix, doRsi);

  /* TQQQ price panel: identical boxes to the RSI panel. NOTE: price y-axis is
     log scale, so annotation y must be log10(value), else it lands off-screen. */
  if(si>=0 && D.tqqq[si]!=null) trigAnn.push(tbox(t.signal_date, Math.log10(D.tqqq[si]), 'y', sigTxt, '#f0883e',   0, -64));
  trigAnn.push(tbox(t.entry_date, Math.log10(t.entry_price), 'y', buyTxt, '#3fb950',  62, -34));
  if(!t.open) trigAnn.push(tbox(t.exit_date, Math.log10(t.exit_price), 'y', sellTxt, '#f85149', -64, -52));
});

const lastDate = dates[dates.length-1];
const d1y = new Date(lastDate); d1y.setFullYear(d1y.getFullYear()-1);
const init = d1y.toISOString().slice(0,10);

const layout = {
  paper_bgcolor:'#1a2029', plot_bgcolor:'#1a2029', font:{color:'#9aa7b4',size:12},
  showlegend:true, legend:{orientation:'h',y:1.005,x:0,yanchor:'bottom',font:{color:'#e6edf3'}},
  margin:{l:55,r:20,t:10,b:30}, hovermode:'x unified', dragmode:'zoom',
  annotations:trigAnn,
  xaxis:{domain:[0,1],anchor:'y3',gridcolor:'#2d333b',range:[init,lastDate],
    rangeslider:{visible:false},
    rangebreaks:[{bounds:['sat','mon']},{values:D.holidays}],
    rangeselector:{bgcolor:'#0f1419',activecolor:'#f0883e',bordercolor:'#2d333b',borderwidth:1,
      font:{color:'#e6edf3'},x:0,y:1.03,yanchor:'bottom',
      buttons:[
        {count:3,label:'3M',step:'month',stepmode:'backward'},
        {count:6,label:'6M',step:'month',stepmode:'backward'},
        {count:1,label:'1Y',step:'year',stepmode:'backward'},
        {count:3,label:'3Y',step:'year',stepmode:'backward'},
        {step:'all',label:'Max'}]}},
  yaxis:{domain:[0.42,1],title:'TQQQ 价格 ($)',type:'log',gridcolor:'#2d333b'},
  yaxis2:{domain:[0.22,0.39],title:'VIX',gridcolor:'#2d333b'},
  yaxis3:{domain:[0.02,0.19],title:'RSI(14)',gridcolor:'#2d333b'},
  shapes:[
    {type:'line',xref:'paper',x0:0,x1:1,yref:'y2',y0:D.thresholds.vix,y1:D.thresholds.vix,
      line:{color:'#f85149',width:1,dash:'dash'}},
    {type:'line',xref:'paper',x0:0,x1:1,yref:'y3',y0:D.thresholds.rsi,y1:D.thresholds.rsi,
      line:{color:'#f85149',width:1,dash:'dash'}}],
};

const gd=document.getElementById('chart');
let scaling=false;
function autoscaleY(full){
  let x0=-Infinity,x1=Infinity;
  if(!full){ const xr=gd.layout.xaxis&&gd.layout.xaxis.range;
    if(xr){ x0=new Date(xr[0]).getTime(); x1=new Date(xr[1]).getTime(); } }
  let pl=Infinity,ph=-Infinity,vl=Infinity,vh=-Infinity,rl=Infinity,rh=-Infinity;
  for(let i=0;i<dates.length;i++){
    const tm=new Date(dates[i]).getTime();
    if(tm<x0||tm>x1) continue;
    const lo=D.tqqq_low[i],hi=D.tqqq_high[i];
    if(lo!=null&&lo<pl)pl=lo; if(hi!=null&&hi>ph)ph=hi;
    const v=D.vix[i]; if(v!=null){if(v<vl)vl=v;if(v>vh)vh=v;}
    const r=D.rsi[i]; if(r!=null){if(r<rl)rl=r;if(r>rh)rh=r;}
  }
  if(!isFinite(pl)||!isFinite(ph)) return;
  const upd={'yaxis.range':[Math.log10(pl*0.95),Math.log10(ph*1.05)]};
  if(isFinite(vl)){ const lo=Math.min(vl,D.thresholds.vix),hi=Math.max(vh,D.thresholds.vix),
    p=Math.max(1,(hi-lo)*0.1); upd['yaxis2.range']=[Math.max(0,lo-p),hi+p]; }
  if(isFinite(rl)){ const lo=Math.min(rl,D.thresholds.rsi),hi=Math.max(rh,D.thresholds.rsi),
    p=Math.max(1,(hi-lo)*0.1); upd['yaxis3.range']=[lo-p,hi+p]; }
  scaling=true; Plotly.relayout(gd,upd).then(()=>{scaling=false;});
}

Plotly.newPlot(gd,[price,entry,exit,vix,rsi],layout,
  {scrollZoom:true,responsive:true,displaylogo:false,
   modeBarButtonsToRemove:['lasso2d','select2d']}).then(()=>{
  autoscaleY(false);
  gd.on('plotly_relayout',(ev)=>{
    if(scaling) return;
    if('xaxis.autorange' in ev) autoscaleY(true);
    else if(('xaxis.range[0]' in ev)||('xaxis.range' in ev)) autoscaleY(false);
  });
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Dashboard -> http://localhost:{port}  (Ctrl-C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
