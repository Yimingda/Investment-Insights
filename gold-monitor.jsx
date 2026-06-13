import { useState, useEffect, useRef, useCallback } from "react";

// ── Constants ────────────────────────────────────────────────
const MACRO = {
  cpi: 4.2, ath: 5595, yearAgo: 3192, ma200: 4480,
  tips: 1.85, dxy: 102.8, rsi: 38, etfFlow: -0.38,
  hikeProb: 70, cbQ1: 244,
};
const INSTITUTIONS = [
  { name: "JPMorgan",       target: 6000, note: "年末目标，下修自 $5,708" },
  { name: "富国银行",        target: 6200, note: "最激进 $6,100–6,300" },
  { name: "高盛",            target: 5400, note: "维持不变，最具韧性" },
  { name: "UBS 瑞银",        target: 5500, note: "下修自 $5,900" },
  { name: "Morgan Stanley",  target: 5200, note: "下修，仍看多结构" },
  { name: "LBMA 共识均价",   target: 4742, note: "28位分析师全年均价" },
];
const WATCHLIST = [
  { name: "白银 Silver",   ticker: "XAG/USD", price: 32.45, chg: -0.82 },
  { name: "黄金ETF",       ticker: "GLD",     price: 391.2, chg: -0.35 },
  { name: "黄金矿业ETF",   ticker: "GDX",     price: 38.9,  chg: -1.2  },
  { name: "美元指数",       ticker: "DXY",     price: 102.8, chg: 0.18  },
  { name: "美国10Y国债",   ticker: "US10Y",   price: 4.38,  chg: 0.03, isRate: true },
  { name: "原油 WTI",      ticker: "CL",      price: 99.8,  chg: 1.45  },
];
const RISK_FACTORS = [
  { label: "美联储鹰派风险", val: "高", pct: 80, color: "#e05555" },
  { label: "通胀粘性支撑",   val: "强", pct: 75, color: "#3dba6a" },
  { label: "央行结构需求",   val: "强", pct: 85, color: "#3dba6a" },
  { label: "ETF资金流入",    val: "弱", pct: 25, color: "#e05555" },
  { label: "美元走强压力",   val: "高", pct: 70, color: "#e05555" },
  { label: "地缘风险溢价",   val: "中", pct: 60, color: "#e08030" },
];

const BASE_HISTORY = [
  4530,4503,4462,4410,4380,4320,4360,4344,4310,4290,
  4265,4083,4120,4150,4180,4219,4210,4195,4220,4205,
  4190,4215,4230,4219,4205,4190,4218,4210,4195,4219,
];

// ── Helpers ──────────────────────────────────────────────────
function fmt(n) { return "$" + Math.round(n).toLocaleString(); }
function calcScore(price) {
  let s = 50;
  if (price < MACRO.ma200) s -= 10; else s += 5;
  if (MACRO.rsi < 30) s += 8; else if (MACRO.rsi < 40) s += 3; else if (MACRO.rsi > 70) s -= 8;
  if (MACRO.etfFlow > 0) s += 6; else s -= 4;
  if (MACRO.tips < 0) s += 8; else if (MACRO.tips < 1) s += 3; else if (MACRO.tips > 2) s -= 6;
  if (MACRO.dxy > 105) s -= 5; else if (MACRO.dxy < 100) s += 5;
  if (MACRO.hikeProb > 60) s -= 6; else if (MACRO.hikeProb < 30) s += 6;
  s += 5;
  if ((MACRO.ath - price) / MACRO.ath > 0.2) s += 5;
  return Math.max(5, Math.min(95, Math.round(s)));
}

// ── Sub-components ───────────────────────────────────────────

// Gauge (SVG)
function Gauge({ score }) {
  const cx = 120, cy = 100, r = 78;
  const segments = [
    { from: Math.PI,      to: Math.PI * 1.2, color: "#7f1d1d" },
    { from: Math.PI*1.2,  to: Math.PI * 1.4, color: "#991b1b" },
    { from: Math.PI*1.4,  to: Math.PI * 1.6, color: "#5c3d00" },
    { from: Math.PI*1.6,  to: Math.PI * 1.8, color: "#14532d" },
    { from: Math.PI*1.8,  to: Math.PI * 2,   color: "#052e16" },
  ];
  const angle = Math.PI + (score / 100) * Math.PI;
  const nx = cx + (r - 5) * Math.cos(angle);
  const ny = cy + (r - 5) * Math.sin(angle);
  const arcPath = (from, to) => {
    const x1 = cx + r * Math.cos(from), y1 = cy + r * Math.sin(from);
    const x2 = cx + r * Math.cos(to),   y2 = cy + r * Math.sin(to);
    return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
  };
  const label = score >= 65 ? { t: "积极看多", c: "#3dba6a" }
              : score >= 50 ? { t: "温和看多", c: "#3dba6a" }
              : score >= 40 ? { t: "中性观望", c: "#e08030" }
              : score >= 30 ? { t: "偏空谨慎", c: "#e08030" }
              :               { t: "明显看空", c: "#e05555" };
  return (
    <svg viewBox="0 0 240 130" style={{ width: "100%", maxWidth: 220 }}>
      {segments.map((s, i) => (
        <path key={i} d={arcPath(s.from, s.to)} stroke={s.color} strokeWidth={18} fill="none" />
      ))}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#f0c040" strokeWidth={2.5} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={6} fill="#f0c040" />
      <text x={cx-62} y={cy+14} fill="#5a6070" fontSize={9} textAnchor="middle">极度看空</text>
      <text x={cx}    y={cy-r-6} fill="#5a6070" fontSize={9} textAnchor="middle">中性</text>
      <text x={cx+62} y={cy+14} fill="#5a6070" fontSize={9} textAnchor="middle">极度看多</text>
      <text x={cx} y={cy+32} fill="#e4e6ee" fontSize={20} fontWeight="bold" textAnchor="middle" fontFamily="monospace">{score}</text>
      <text x={cx} y={cy+46} fill="#5a6070" fontSize={10} textAnchor="middle">综合得分 / 100</text>
      <text x={cx} y={cy+62} fill={label.c} fontSize={12} fontWeight="600" textAnchor="middle">{label.t}</text>
    </svg>
  );
}

// Mini Price Chart (SVG)
function PriceChart({ history, price }) {
  const prices = [...history.slice(-29), price];
  const min = Math.min(...prices) - 60;
  const max = Math.max(...prices) + 60;
  const range = max - min;
  const W = 540, H = 160;
  const pad = { l: 52, r: 20, t: 14, b: 28 };
  const cW = W - pad.l - pad.r, cH = H - pad.t - pad.b;
  const px = (i) => pad.l + (i / (prices.length - 1)) * cW;
  const py = (p) => pad.t + (1 - (p - min) / range) * cH;
  const pts = prices.map((p, i) => `${px(i)},${py(p)}`).join(" ");
  const fill = `${pts} ${px(prices.length-1)},${H-pad.b} ${pad.l},${H-pad.b}`;
  const ma200y = py(MACRO.ma200);
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map(t => ({
    y: pad.t + t * cH, val: Math.round(max - t * range),
  }));
  const xLabels = [
    { i: 0, t: "5/16" }, { i: 4, t: "5/21" }, { i: 9, t: "5/26" },
    { i: 14, t: "5/31" }, { i: 19, t: "6/5" }, { i: 24, t: "6/10" }, { i: 29, t: "今日" },
  ];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 180 }}>
      <defs>
        <linearGradient id="gfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#d4a520" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#d4a520" stopOpacity="0" />
        </linearGradient>
      </defs>
      {yLabels.map((l, i) => (
        <g key={i}>
          <line x1={pad.l} y1={l.y} x2={W-pad.r} y2={l.y} stroke="#1e2130" strokeWidth={0.5} />
          <text x={pad.l-4} y={l.y+3} fill="#5a6070" fontSize={9} textAnchor="end" fontFamily="monospace">${l.val.toLocaleString()}</text>
        </g>
      ))}
      {/* MA200 */}
      <line x1={pad.l} y1={ma200y} x2={W-pad.r} y2={ma200y} stroke="#e08030" strokeWidth={1} strokeDasharray="4 3" />
      <text x={W-pad.r} y={ma200y-4} fill="#e08030" fontSize={9} textAnchor="end">MA200</text>
      {/* Fill */}
      <polygon points={fill} fill="url(#gfill)" />
      {/* Line */}
      <polyline points={pts} fill="none" stroke="#d4a520" strokeWidth={2} strokeLinejoin="round" />
      {/* Dot */}
      <circle cx={px(prices.length-1)} cy={py(price)} r={4} fill="#f0c040" stroke="#0a0c10" strokeWidth={1.5} />
      {/* X labels */}
      {xLabels.map((l, i) => (
        <text key={i} x={px(l.i)} y={H-pad.b+14} fill="#5a6070" fontSize={9} textAnchor="middle">{l.t}</text>
      ))}
    </svg>
  );
}

// ── Main App ─────────────────────────────────────────────────
export default function GoldMonitor() {
  const [price, setPrice]           = useState(4219);
  const [prevPrice, setPrevPrice]   = useState(4219);
  const [history, setHistory]       = useState(BASE_HISTORY);
  const [lastUpdate, setLastUpdate] = useState("—");
  const [activeTab, setActiveTab]   = useState("long");
  const [aiText, setAiText]         = useState(null);
  const [aiLoading, setAiLoading]   = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const scoreRef = useRef(calcScore(4219));

  // Simulate price tick
  const tick = useCallback((cur) => {
    const drift = (Math.random() - 0.48) * 12;
    const noise = (Math.random() - 0.5) * 6;
    return Math.max(3800, Math.min(4700, parseFloat((cur + drift + noise).toFixed(2))));
  }, []);

  const doRefresh = useCallback(() => {
    setRefreshing(true);
    setPrice(p => {
      const np = tick(p);
      setPrevPrice(p);
      scoreRef.current = calcScore(np);
      setHistory(h => [...h.slice(-59), np]);
      return np;
    });
    setLastUpdate(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    setTimeout(() => setRefreshing(false), 400);
  }, [tick]);

  // Auto-refresh 30s
  useEffect(() => {
    doRefresh();
    const id = setInterval(doRefresh, 30000);
    return () => clearInterval(id);
  }, []);

  // AI call
  const runAI = useCallback(async () => {
    setAiLoading(true);
    setAiText(null);
    const score = calcScore(price);
    const prompt = `你是一位专业的黄金投资分析师。请基于以下实时市场数据，给出简洁、客观的分析。
输出格式：严格输出三段纯文本，每段之间用空行分隔，不要加粗、不要标题符号、不要markdown。
第一段：当前形势判断（2-3句）
第二段：最值得关注的风险（2-3句）
第三段：给普通投资者的一句话建议

数据：
- 黄金现货：$${price}（较年初ATH $5,595 跌 ${(((price-5595)/5595)*100).toFixed(1)}%）
- 200日均线：$${MACRO.ma200}（金价${price > MACRO.ma200 ? "上方" : "下方"}）
- RSI(14)：${MACRO.rsi} / DXY：${MACRO.dxy} / 10Y TIPS：${MACRO.tips}%
- ETF本周净流量：${MACRO.etfFlow} MOz / 美国CPI：${MACRO.cpi}%
- 12月加息概率：${MACRO.hikeProb}% / Q1央行净购：${MACRO.cbQ1}吨
- 机构目标价中位：$5,400 / 综合信号得分：${score}/100`;

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          messages: [{ role: "user", content: prompt }],
        }),
      });
      const data = await res.json();
      const raw = (data.content || []).map(c => c.text || "").join("");
      setAiText(raw.trim());
    } catch (e) {
      setAiText("__error__");
    }
    setAiLoading(false);
  }, [price]);

  // Run AI on first load
  useEffect(() => { runAI(); }, []);

  // ── Derived values ─────────────────────────────────────────
  const score    = calcScore(price);
  const change   = price - prevPrice;
  const changePct = prevPrice ? (change / prevPrice * 100) : 0;
  const fromAth  = ((price - MACRO.ath) / MACRO.ath * 100);
  const yoy      = price - MACRO.yearAgo;
  const yoyPct   = (yoy / MACRO.yearAgo * 100);
  const upside   = ((5400 - price) / price * 100);

  const sentColor = score >= 60 ? "#3dba6a" : score >= 40 ? "#e08030" : "#e05555";
  const sentLabel = score >= 65 ? "积极看多" : score >= 50 ? "温和看多" : score >= 40 ? "中性观望" : score >= 30 ? "偏空谨慎" : "明显看空";

  // ── Indicators ─────────────────────────────────────────────
  const indicators = [
    {
      name: "200日均线", val: fmt(MACRO.ma200),
      badge: price > MACRO.ma200 ? ["上方 看多","#3dba6a","rgba(61,186,106,.15)"] : ["下方 看空","#e05555","rgba(224,85,85,.15)"],
    },
    {
      name: "RSI (14)", val: MACRO.rsi,
      badge: MACRO.rsi < 30 ? ["超卖","#3dba6a","rgba(61,186,106,.15)"]
           : MACRO.rsi < 45 ? ["偏弱","#e08030","rgba(224,128,48,.15)"]
           : MACRO.rsi > 70 ? ["超买","#e05555","rgba(224,85,85,.15)"]
           :                  ["中性","#5a6070","rgba(90,96,112,.2)"],
    },
    {
      name: "美元指数 DXY", val: MACRO.dxy,
      badge: MACRO.dxy > 105 ? ["强势 压制金价","#e05555","rgba(224,85,85,.15)"]
           : MACRO.dxy < 99  ? ["弱势 利好黄金","#3dba6a","rgba(61,186,106,.15)"]
           :                   ["中性","#e08030","rgba(224,128,48,.15)"],
    },
    {
      name: "10Y TIPS实际利率", val: MACRO.tips.toFixed(2) + "%",
      badge: MACRO.tips < 0 ? ["负利率 极佳","#3dba6a","rgba(61,186,106,.15)"]
           : MACRO.tips < 1 ? ["低利率 利好","#3dba6a","rgba(61,186,106,.15)"]
           : MACRO.tips > 2 ? ["高利率 压制","#e05555","rgba(224,85,85,.15)"]
           :                  ["中性偏空","#e08030","rgba(224,128,48,.15)"],
    },
    {
      name: "ETF资金流向(本周)", val: (MACRO.etfFlow >= 0 ? "+" : "") + MACRO.etfFlow + " MOz",
      badge: MACRO.etfFlow > 0.3  ? ["强净流入","#3dba6a","rgba(61,186,106,.15)"]
           : MACRO.etfFlow > 0    ? ["小幅流入","#3dba6a","rgba(61,186,106,.15)"]
           : MACRO.etfFlow > -0.2 ? ["小幅流出","#e08030","rgba(224,128,48,.15)"]
           :                        ["明显流出","#e05555","rgba(224,85,85,.15)"],
    },
  ];

  // ── Alerts ─────────────────────────────────────────────────
  const alerts = [];
  if (price < MACRO.ma200) alerts.push({ type:"warn", icon:"⚠️", text:`金价 (${fmt(price)}) 跌破200日均线（${fmt(MACRO.ma200)}），技术面偏空。` });
  if (MACRO.etfFlow < -0.3) alerts.push({ type:"dn", icon:"📉", text:`黄金ETF本周净流出 ${Math.abs(MACRO.etfFlow)} MOz，短期动量不佳。` });
  if (MACRO.hikeProb > 60)  alerts.push({ type:"warn", icon:"🏦", text:`CME定价12月加息概率 ${MACRO.hikeProb}%，FOMC（6/16-17）是本月最大催化剂。` });
  if (MACRO.cbQ1 >= 200)    alerts.push({ type:"up", icon:"✅", text:`Q1全球央行净购金 ${MACRO.cbQ1} 吨，结构性需求底盘稳固。` });

  // ── Scenario content ────────────────────────────────────────
  const stopL  = Math.round(price * 0.92);
  const entry2 = Math.round(price * 0.95);
  const scenarios = {
    long: [
      { dot:"#3dba6a", text: `当前入场评级：${price < MACRO.ma200 ? "⭐⭐ 等待或小仓试探" : "⭐⭐⭐ 可以分批建仓"}` },
      { dot:"#3dba6a", text: `建仓策略：将资金分4份，每隔4-6周买入一份，首批本周起始。` },
      { dot:"#3dba6a", text: `仓位上限：黄金占总投资组合不超过 15%。` },
      { dot:"#e08030", text: `机构目标价中位 $5,400，较当前上行约 +${upside.toFixed(0)}%（12个月维度）。` },
      { dot:"#e05555", text: `止损参考：若月度收盘价跌破 $3,500，需重新评估整体逻辑。` },
      { dot:"#5b9cf6", text: `低成本加仓点：若进一步下探 $${entry2}（-5%），可加大第二批力度。` },
    ],
    mid: [
      { dot:"#e08030", text: `关键决策节点：等待 6月16-17日 FOMC 结果落地，不提前押注方向。` },
      { dot:"#3dba6a", text: `看多触发：若Warsh点阵图暗示暂停加息，金价有望快速反弹至 $4,500+，届时右侧入场。` },
      { dot:"#e05555", text: `看空触发：若确认12月加息，等待下探至 $3,800–$3,900 区间再建仓。` },
      { dot:"#e08030", text: `目标价位：$4,700–$5,000（3-6个月内）；LBMA全年均价共识 $4,742。` },
      { dot:"#e05555", text: `止损：入场后跌破 $${stopL}（入场价-8%）触发止损。` },
    ],
    short: [
      { dot:"#e05555", text: `当前信号：⛔ 不建议短线做多。跌破200均线 + ETF净流出 + FOMC方向未明。` },
      { dot:"#e08030", text: `若必须操作：严格小仓（≤2%资金），设定硬止损 $${stopL}。` },
      { dot:"#5b9cf6", text: `观察指标：实时跟踪 DXY 和 10Y TIPS 实际利率，与金价反向关系明确。` },
      { dot:"#3dba6a", text: `可做空机会：若FOMC后DXY突破106，金价可能短线下探$3,900，CFD/期货可考虑短空。` },
      { dot:"#5a6070", text: `⚠️ 短线做空黄金需专业知识和严格风险管理，新手请谨慎。` },
    ],
    hold: [
      { dot:"#5b9cf6", text: `持仓评估：若入场成本低于 $4,000，目前仍在浮盈区间，无需恐慌。` },
      { dot:"#3dba6a", text: `持有理由检验：央行需求底盘稳固，LBMA全年均价共识 $4,742 仍高于当前价。` },
      { dot:"#e08030", text: `减仓时机：若价格快速反弹至 $4,700–$5,000，可考虑减持30%锁定部分利润。` },
      { dot:"#e05555", text: `止损纪律：若成本在 $4,200+ 且当前浮亏，跌破 $3,800 必须执行止损。` },
      { dot:"#d4a520", text: `组合再平衡：黄金占比超过总资产15%的部分，建议逢高逐步减至目标仓位。` },
    ],
  };

  const tabCfg = {
    long:  { label: "🟢 长线 >12月",  activeClass: { background:"rgba(61,186,106,.12)", borderColor:"#3dba6a", color:"#3dba6a" } },
    mid:   { label: "🟡 中线 3-6月",  activeClass: { background:"rgba(224,128,48,.12)", borderColor:"#e08030", color:"#e08030" } },
    short: { label: "🔴 短线 <1月",   activeClass: { background:"rgba(224,85,85,.12)", borderColor:"#e05555", color:"#e05555" } },
    hold:  { label: "🔵 已持仓者",    activeClass: { background:"rgba(91,156,246,.12)", borderColor:"#5b9cf6", color:"#5b9cf6" } },
  };

  // ── AI text parsing ─────────────────────────────────────────
  const aiParas = aiText && aiText !== "__error__"
    ? aiText.split(/\n\n+/).filter(Boolean)
    : null;
  const aiHeadings = ["当前形势", "主要风险", "投资者建议"];

  // ── Styles ──────────────────────────────────────────────────
  const S = {
    app: { background:"#0a0c10", minHeight:"100vh", fontFamily:"Inter, system-ui, sans-serif", color:"#e4e6ee", fontSize:13 },
    header: { background:"#111318", borderBottom:"1px solid #1e2130", padding:"0 20px", height:52, display:"flex", alignItems:"center", justifyContent:"space-between", position:"sticky", top:0, zIndex:100 },
    logo: { display:"flex", alignItems:"center", gap:10, fontFamily:"monospace", fontSize:15, fontWeight:500, color:"#f0c040", letterSpacing:"0.04em" },
    logoIcon: { width:28, height:28, background:"#d4a520", borderRadius:6, display:"flex", alignItems:"center", justifyContent:"center", fontSize:13, fontWeight:700, color:"#000" },
    btn: { background:"#181b22", border:"1px solid #1e2130", color:"#f0c040", borderRadius:6, padding:"5px 12px", fontSize:12, cursor:"pointer" },
    main: { padding:"16px 20px", display:"flex", flexDirection:"column", gap:14 },
    kpiStrip: { display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:10 },
    kpi: { background:"#111318", border:"1px solid #1e2130", borderRadius:10, padding:"12px 14px" },
    kpiLabel: { fontSize:10, color:"#5a6070", textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:5 },
    kpiVal: { fontFamily:"monospace", fontSize:20, fontWeight:500 },
    kpiSub: { fontSize:11, marginTop:2 },
    grid2: { display:"grid", gridTemplateColumns:"1fr 1fr", gap:14 },
    grid3: { display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:14 },
    card: { background:"#111318", border:"1px solid #1e2130", borderRadius:10, overflow:"hidden" },
    cardHead: { padding:"10px 14px", borderBottom:"1px solid #1e2130", fontSize:11, fontWeight:600, color:"#5a6070", textTransform:"uppercase", letterSpacing:"0.08em", display:"flex", alignItems:"center", justifyContent:"space-between" },
    cardBody: { padding:14 },
    indRow: { display:"flex", justifyContent:"space-between", alignItems:"center", padding:"7px 0", borderBottom:"1px solid #1e2130" },
    badge: (c,bg) => ({ display:"inline-block", padding:"2px 7px", borderRadius:4, fontSize:10, fontWeight:600, textTransform:"uppercase", letterSpacing:"0.05em", color:c, background:bg }),
    alertBar: (type) => {
      const m = { up:["rgba(61,186,106,.08)","rgba(61,186,106,.25)"], warn:["rgba(224,128,48,.08)","rgba(224,128,48,.25)"], dn:["rgba(224,85,85,.08)","rgba(224,85,85,.25)"] };
      return { borderRadius:7, padding:"9px 12px", marginBottom:8, display:"flex", alignItems:"flex-start", gap:8, background:m[type][0], border:`1px solid ${m[type][1]}`, fontSize:12 };
    },
  };

  return (
    <div style={S.app}>
      {/* Header */}
      <div style={S.header}>
        <div style={S.logo}>
          <div style={S.logoIcon}>Au</div>
          Au Watch · 黄金行情监控
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <span style={{ fontFamily:"monospace", fontSize:11, color:"#5a6070" }}>{lastUpdate}</span>
          <button style={S.btn} onClick={doRefresh} disabled={refreshing}>
            {refreshing ? "刷新中…" : "⟳ 刷新"}
          </button>
        </div>
      </div>

      <div style={S.main}>
        {/* KPI Strip */}
        <div style={S.kpiStrip}>
          {[
            { label:"现货价格 XAU/USD", val: fmt(price), valColor:"#f0c040",
              sub: `${change>=0?"+":""}$${Math.round(change)} (${changePct.toFixed(2)}%)`, subColor: change>=0?"#3dba6a":"#e05555" },
            { label:"距年初高点", val: fromAth.toFixed(1)+"%", valColor:"#e05555",
              sub: "ATH $5,595（1月28日）", subColor:"#5a6070" },
            { label:"年同比涨幅", val: `+$${Math.round(yoy).toLocaleString()}`, valColor:"#3dba6a",
              sub: `同比 +${yoyPct.toFixed(1)}%`, subColor:"#3dba6a" },
            { label:"机构目标价中位", val: "$5,400", valColor:"#f0c040",
              sub: `↑ 上行空间 +${upside.toFixed(0)}%`, subColor:"#3dba6a" },
            { label:"市场情绪", val: sentLabel, valColor: sentColor,
              sub: `综合得分 ${score}/100`, subColor: sentColor },
          ].map((k,i) => (
            <div key={i} style={S.kpi}>
              <div style={S.kpiLabel}>{k.label}</div>
              <div style={{ ...S.kpiVal, color:k.valColor }}>{k.val}</div>
              <div style={{ ...S.kpiSub, color:k.subColor }}>{k.sub}</div>
            </div>
          ))}
        </div>

        {/* Alerts */}
        <div>
          {alerts.map((a,i) => (
            <div key={i} style={S.alertBar(a.type)}>
              <span style={{ fontSize:14, flexShrink:0 }}>{a.icon}</span>
              <span>{a.text}</span>
            </div>
          ))}
        </div>

        {/* Chart + Gauge */}
        <div style={S.grid2}>
          <div style={S.card}>
            <div style={S.cardHead}><span>价格走势（近30日）</span><span>橙线 = MA200</span></div>
            <div style={{ padding:"10px 6px 6px" }}>
              <PriceChart history={history} price={price} />
            </div>
          </div>
          <div style={S.card}>
            <div style={S.cardHead}><span>综合信号仪表盘</span></div>
            <div style={{ ...S.cardBody, display:"flex", flexDirection:"column", alignItems:"center", gap:4 }}>
              <Gauge score={score} />
              <div style={{ width:"100%", marginTop:4 }}>
                {indicators.map((ind,i) => (
                  <div key={i} style={{ ...S.indRow, ...(i===indicators.length-1?{borderBottom:"none"}:{}) }}>
                    <span style={{ color:"#5a6070", fontSize:12 }}>{ind.name}</span>
                    <span style={{ fontFamily:"monospace", fontSize:12 }}>{ind.val}</span>
                    <span style={S.badge(ind.badge[1], ind.badge[2])}>{ind.badge[0]}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Strategies + AI */}
        <div style={S.grid2}>
          {/* Strategies */}
          <div style={S.card}>
            <div style={S.cardHead}><span>投资策略推荐</span><span>选择持仓周期</span></div>
            <div style={S.cardBody}>
              {/* Tabs */}
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:6, marginBottom:12 }}>
                {Object.entries(tabCfg).map(([key, cfg]) => {
                  const isActive = activeTab === key;
                  return (
                    <button key={key} onClick={() => setActiveTab(activeTab===key?null:key)}
                      style={{ border:"1px solid", borderRadius:6, padding:"7px 4px", cursor:"pointer", fontSize:11, fontWeight:600, textAlign:"center", transition:"all .15s", fontFamily:"inherit",
                        ...(isActive ? cfg.activeClass : { background:"#181b22", borderColor:"#1e2130", color:"#5a6070" }) }}>
                      {cfg.label}
                    </button>
                  );
                })}
              </div>
              {/* Content */}
              {activeTab && (
                <div style={{ borderRadius:8, padding:"12px 14px", fontSize:12, lineHeight:1.8,
                  background: activeTab==="long"?"rgba(61,186,106,.06)":activeTab==="mid"?"rgba(224,128,48,.06)":activeTab==="short"?"rgba(224,85,85,.06)":"rgba(91,156,246,.06)",
                  border: `1px solid ${activeTab==="long"?"rgba(61,186,106,.2)":activeTab==="mid"?"rgba(224,128,48,.2)":activeTab==="short"?"rgba(224,85,85,.2)":"rgba(91,156,246,.2)"}`,
                }}>
                  {scenarios[activeTab].map((item,i) => (
                    <div key={i} style={{ display:"flex", gap:8, marginBottom:5 }}>
                      <div style={{ width:5, height:5, borderRadius:"50%", background:item.dot, marginTop:6, flexShrink:0 }} />
                      <div>{item.text}</div>
                    </div>
                  ))}
                </div>
              )}
              {!activeTab && (
                <div style={{ textAlign:"center", color:"#5a6070", padding:"20px 0", fontSize:12 }}>
                  ↑ 点击上方按钮查看对应策略建议
                </div>
              )}
            </div>
          </div>

          {/* AI Analysis */}
          <div style={S.card}>
            <div style={S.cardHead}>
              <span>🤖 AI 实时分析</span>
              <button style={{ ...S.btn, fontSize:11, padding:"3px 10px" }} onClick={runAI} disabled={aiLoading}>
                {aiLoading ? "分析中…" : "重新分析"}
              </button>
            </div>
            <div style={S.cardBody}>
              <div style={{ background:"#181b22", border:"1px solid #1e2130", borderRadius:8, padding:14, fontSize:13, lineHeight:1.85, minHeight:140 }}>
                {aiLoading && (
                  <div style={{ color:"#5a6070", display:"flex", alignItems:"center", gap:8 }}>
                    <div style={{ width:14, height:14, border:"2px solid #1e2130", borderTopColor:"#d4a520", borderRadius:"50%", animation:"spin .8s linear infinite" }} />
                    Claude 正在分析当前黄金市场数据…
                  </div>
                )}
                {!aiLoading && aiText === "__error__" && (
                  <div style={{ color:"#e05555" }}>⚠️ 分析请求失败，请点击「重新分析」重试。</div>
                )}
                {!aiLoading && aiParas && aiParas.map((p, i) => (
                  <div key={i} style={{ marginBottom: i < aiParas.length-1 ? 12 : 0 }}>
                    <div style={{ fontSize:10, textTransform:"uppercase", letterSpacing:"0.08em", color:"#d4a520", marginBottom:4, fontWeight:600 }}>
                      {aiHeadings[i] || ""}
                    </div>
                    <div>{p}</div>
                  </div>
                ))}
                {!aiLoading && !aiText && (
                  <div style={{ color:"#5a6070" }}>点击「重新分析」获取 AI 解读</div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Institutions + Heatmap + Watchlist */}
        <div style={S.grid3}>
          {/* Institutions */}
          <div style={S.card}>
            <div style={S.cardHead}><span>机构目标价</span></div>
            <div style={S.cardBody}>
              {INSTITUTIONS.map((inst,i) => {
                const pct = Math.round(((inst.target-price)/price)*100);
                const barW = Math.round((inst.target/6300)*100);
                const c = pct>20?"#4ade80":pct>10?"#fbbf24":"#f87171";
                return (
                  <div key={i} style={{ marginBottom:10 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, marginBottom:3 }}>
                      <span style={{ color:"#5a6070" }}>{inst.name}</span>
                      <span style={{ fontFamily:"monospace", color:"#f0c040" }}>
                        ${inst.target.toLocaleString()} <span style={{ color:c, fontSize:10 }}>(+{pct}%)</span>
                      </span>
                    </div>
                    <div style={{ height:5, background:"#1e2130", borderRadius:3, overflow:"hidden" }}>
                      <div style={{ height:"100%", width:barW+"%", background:"linear-gradient(90deg,#8b6914,#f0c040)", borderRadius:3 }} />
                    </div>
                    <div style={{ fontSize:9, color:"#5a6070", marginTop:2 }}>{inst.note}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Heatmap */}
          <div style={S.card}>
            <div style={S.cardHead}><span>风险因子热力图</span></div>
            <div style={S.cardBody}>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                {RISK_FACTORS.map((f,i) => (
                  <div key={i} style={{ borderRadius:6, padding:"9px 11px", background:`${f.color}18` }}>
                    <div style={{ fontSize:10, color:"rgba(255,255,255,.55)", marginBottom:2 }}>{f.label}</div>
                    <div style={{ fontSize:13, fontWeight:600, color:f.color }}>{f.val}</div>
                    <div style={{ height:3, background:"rgba(255,255,255,.12)", borderRadius:2, marginTop:4 }}>
                      <div style={{ height:"100%", width:f.pct+"%", background:f.color, borderRadius:2, opacity:.7 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Watchlist */}
          <div style={S.card}>
            <div style={S.cardHead}><span>相关资产监控</span></div>
            <div style={S.cardBody}>
              {WATCHLIST.map((a,i) => {
                const up = a.chg >= 0;
                const val = a.isRate ? a.price.toFixed(2)+"%" : "$"+a.price.toFixed(2);
                const chgStr = (up?"+":"")+a.chg.toFixed(2)+(a.isRate?"bp":"%");
                return (
                  <div key={i} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"8px 0", borderBottom: i<WATCHLIST.length-1?"1px solid #1e2130":"none" }}>
                    <div>
                      <div style={{ fontSize:12 }}>{a.name}</div>
                      <div style={{ fontSize:10, color:"#5a6070" }}>{a.ticker}</div>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontFamily:"monospace", fontSize:12 }}>{val}</div>
                      <div style={{ fontSize:10, color: up?"#3dba6a":"#e05555" }}>{chgStr}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Disclaimer */}
        <div style={{ fontSize:10, color:"#3a3e4a", textAlign:"center", paddingBottom:8 }}>
          ⚠️ 本工具仅供参考，不构成投资建议。黄金投资存在本金损失风险，请结合自身风险承受能力审慎决策。
        </div>
      </div>

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
