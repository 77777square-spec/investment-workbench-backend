#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投资顾问 AI 工作台 · Streamlit 版（单文件，免费部署到 Streamlit Community Cloud）
- 今日工作：可添加 / 打勾 / 进度统计（会话内持久）
- 四大面板：美股速览+三大指数 / A股热话题 / 日韩14-15点 / A股15点收盘资金流
- 数据：A股指数/美股指数/日韩 = Tushare；A股板块资金流 = 东方财富；美股板块/个股 = Yahoo
- 任何一项拉不到自动用演示数据补齐，页面照常可用
- 老师打开网址 -> 侧栏填自己的 32 位 Tushare Token -> 看实时行情

部署：把本文件 + requirements.txt 推到 GitHub 公开仓库，
      打开 https://share.streamlit.io 连接仓库、选 app.py 即可（免费、无需信用卡）。
"""

import json
import time
import urllib.request
import urllib.parse
import concurrent.futures
from datetime import datetime

import streamlit as st

# ===================== 数据层（与 server.py 同源逻辑） =====================
TS_API = "https://api.tushare.pro"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

DEMO = {
    "usStocks": {
        "sectors": [{"name": "科技", "change": 1.82}, {"name": "金融", "change": -0.46}, {"name": "能源", "change": 0.93}],
        "movers": [{"name": "英伟达 NVDA", "change": 3.21}, {"name": "苹果 AAPL", "change": -0.74},
                   {"name": "特斯拉 TSLA", "change": 2.05}, {"name": "摩根大通 JPM", "change": -0.31}]},
    "usIndices": [{"name": "标普500", "change": 0.52}, {"name": "纳斯达克", "change": 1.13},
                  {"name": "道琼斯", "change": -0.21}],
    "aTopics": [
        {"topic": "AI算力/光模块", "heat": 96, "board": "通信/电子"},
        {"topic": "半导体国产替代", "heat": 88, "board": "电子"},
        {"topic": "低空经济", "heat": 81, "board": "军工/机械"},
        {"topic": "中特估/红利", "heat": 74, "board": "银行/石油"}],
    "jpKr": {
        "gov": [{"h": "日本央行维持利率不变，措辞偏鸽", "d": "日元走弱，利好出口股"},
                {"h": "韩国财政部提示外汇波动，必要时干预", "d": "三星电子获支撑"}],
        "stocks": [{"name": "日经225", "change": 1.12}, {"name": "韩国综指", "change": -0.88}]},
    "aClose": {
        "sectors": [{"name": "半导体", "in": 128.4, "out": 96.2}, {"name": "新能源", "in": 54.1, "out": 71.8},
                    {"name": "金融", "in": 42.7, "out": 38.0}],
        "indices": [{"name": "上证指数", "change": 0.62}, {"name": "深证成指", "change": -0.18},
                    {"name": "创业板指", "change": 0.95}],
        "national": [{"h": "国常会：研究促进消费政策", "d": "关注家电/汽车链"},
                     {"h": "央行开展逆回购，流动性平稳", "d": "资金面无虞"},
                     {"h": "证监会：推进中长期资金入市", "d": "利好蓝筹估值"}]
    }
}


def ts_query(token, api_name, params, fields=""):
    payload = json.dumps({"api_name": api_name, "token": token, "params": params, "fields": fields}).encode("utf-8")
    req = urllib.request.Request(TS_API, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        if j.get("code") == 0 and j.get("data"):
            return j["data"]
    except Exception as e:
        print(f"[warn] Tushare {api_name} 失败：{e}")
    return None


def rows(data):
    if not data or not data.get("fields"):
        return []
    f = data["fields"]
    return [dict(zip(f, row)) for row in data.get("items", [])]


def yahoo_change(symbol, timeout=3):
    path = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=5d"
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            req = urllib.request.Request("https://" + host + path, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
            meta = j["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price and prev:
                return round((price - prev) / prev * 100, 2)
        except Exception:
            pass
    return None


def _batch(sym_map, timeout=3):
    def work(sym):
        return sym, yahoo_change(sym, timeout)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        return {s: c for s, c in ex.map(work, sym_map.keys())}


def fetch_us():
    sectors, movers = [], []
    sc = _batch({"XLK": "科技", "XLF": "金融", "XLE": "能源"})
    mv = _batch({"AAPL": "苹果 AAPL", "NVDA": "英伟达 NVDA", "MSFT": "微软 MSFT",
                 "TSLA": "特斯拉 TSLA", "JPM": "摩根大通 JPM"})
    for sym, name in {"XLK": "科技", "XLF": "金融", "XLE": "能源"}.items():
        c = sc.get(sym)
        if c is not None:
            sectors.append({"name": name, "change": c})
    for sym, name in {"AAPL": "苹果 AAPL", "NVDA": "英伟达 NVDA", "MSFT": "微软 MSFT",
                      "TSLA": "特斯拉 TSLA", "JPM": "摩根大通 JPM"}.items():
        c = mv.get(sym)
        if c is not None:
            movers.append({"name": name, "change": c})
    return sectors, movers


def fetch_asia():
    m = _batch({"^N225": "日经225", "^KS11": "韩国综指"})
    out = []
    for sym, name in {"^N225": "日经225", "^KS11": "韩国综指"}.items():
        c = m.get(sym)
        if c is not None:
            out.append({"name": name, "change": c})
    return out


def fetch_global_indices(token, td, mapping):
    out = []
    for code, name in mapping.items():
        d = ts_query(token, "index_global", {"ts_code": code, "trade_date": td}, "pct_chg")
        if d:
            for r in rows(d):
                if "pct_chg" in r:
                    out.append({"name": name, "change": float(r["pct_chg"])})
                    break
    return out


def fetch_sector_flow():
    url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=12&po=1&np=1&fltt=2&invt=2"
           "&fs=m:90+t:2&fields=f12,f14,f62")
    try:
        req = urllib.request.Request(url, headers={**UA, "Referer": "https://quote.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=12) as r:
            j = json.loads(r.read())
        diff = (j.get("data") or {}).get("diff") or []
        res = []
        for it in diff:
            name = it.get("f14")
            net = it.get("f62")
            if name and net is not None:
                res.append({"name": name, "net": round(net / 1e8, 1)})
        return res[:8]
    except Exception as e:
        print(f"[warn] 东方财富板块资金流失败：{e}")
    return None


@st.cache_data(ttl=300)
def build_dashboard(token, date_str):
    note = []
    td = date_str.replace("-", "") if date_str else datetime.now().strftime("%Y%m%d")

    us_sec, us_mov = fetch_us()
    if us_sec and us_mov:
        us_stocks = {"sectors": us_sec, "movers": us_mov}
    else:
        us_stocks = DEMO["usStocks"]; note.append("美股板块/个股(演示)")

    us_indices = fetch_global_indices(token, td, {"SPX": "标普500", "IXIC": "纳斯达克", "DJI": "道琼斯"})
    if not us_indices:
        us_indices = DEMO["usIndices"]; note.append("美股指数(演示)")

    indices = []
    for code, name in {"000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指"}.items():
        d = ts_query(token, "index_daily", {"ts_code": code, "trade_date": td}, "pct_chg")
        if d:
            for r in rows(d):
                if "pct_chg" in r:
                    indices.append({"name": name, "change": float(r["pct_chg"])})
                    break
    if not indices:
        indices = DEMO["aClose"]["indices"]; note.append("A股指数(演示)")

    asia_idx = fetch_global_indices(token, td, {"N225": "日经225", "KS11": "韩国综指"})
    if asia_idx:
        jpkr_stocks = asia_idx
    else:
        asia = fetch_asia()
        jpkr_stocks = asia if asia else DEMO["jpKr"]["stocks"]
        if not asia:
            note.append("日韩(演示)")

    flow = fetch_sector_flow()
    if flow:
        a_close_sectors = [{"name": s["name"],
                            "in": (s["net"] if s["net"] > 0 else 0),
                            "out": (-s["net"] if s["net"] < 0 else 0)} for s in flow]
    else:
        a_close_sectors = DEMO["aClose"]["sectors"]; note.append("资金流(演示)")

    a_topics = DEMO["aTopics"]; note.append("热话题/政策(演示，待接入)")
    jpkr_gov = DEMO["jpKr"]["gov"]
    national = DEMO["aClose"]["national"]

    return {
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M") + (" · 实时" if token else " · 演示"),
        "note": "；".join(note) if note else "全部实时",
        "usStocks": us_stocks,
        "usIndices": us_indices,
        "aTopics": a_topics,
        "jpKr": {"gov": jpkr_gov, "stocks": jpkr_stocks},
        "aClose": {"sectors": a_close_sectors, "indices": indices, "national": national},
    }


# ===================== 界面渲染 =====================
RED = "#e23c3c"    # 涨（A股习惯：红）
GREEN = "#1a9e54"  # 跌（绿）


def pct(v):
    color = RED if v >= 0 else GREEN
    sign = "+" if v >= 0 else ""
    return f'<span style="color:{color};font-weight:700">{sign}{v:.2f}%</span>'


def net_amt(v):
    color = RED if v >= 0 else GREEN
    sign = "+" if v >= 0 else ""
    return f'<span style="color:{color};font-weight:700">{sign}{v:.1f} 亿</span>'


def card(title, body_html):
    return f"""
    <div style="background:#fff;border:1px solid #e6e8ec;border-radius:12px;padding:14px 16px;margin-bottom:14px;
                box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-weight:700;font-size:15px;margin-bottom:10px;color:#1f2329;border-left:4px solid #4c6ef5;padding-left:8px">{title}</div>
      {body_html}
    </div>"""


def rows_html(items, key_name="name", val_fn=None, extra=None):
    h = '<div style="display:flex;flex-direction:column;gap:6px">'
    for it in items:
        name = it[key_name]
        val = val_fn(it) if val_fn else ""
        ex = f'<span style="color:#86909c;font-size:12px;margin-left:auto">{extra(it)}</span>' if extra else ""
        h += f'<div style="display:flex;align-items:center;gap:10px;font-size:14px"><span style="min-width:90px">{name}</span>{val}{ex}</div>'
    return h + "</div>"


# ---- 页面配置 ----
st.set_page_config(page_title="投资顾问 AI 工作台", page_icon="📊", layout="wide")
st.markdown("""
<style>
  .block-container{padding-top:18px}
  .stButton>button{border-radius:8px}
  .todo-done{text-decoration:line-through;color:#86909c}
</style>""", unsafe_allow_html=True)

# ---- 侧栏：配置 ----
with st.sidebar:
    st.title("⚙️ 设置")
    st.caption("老师填自己的 Tushare Token（32位），留空则为演示数据")
    token = st.text_input("Tushare Token", type="password", key="token_input")
    pick = st.date_input("数据日期", datetime.now().date())
    date_str = pick.strftime("%Y-%m-%d")
    if st.button("🔄 刷新数据", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("演示提示：未填 Token 时所有数据为示例，仅展示版式。")

# ---- 数据加载 ----
data = build_dashboard(token.strip(), date_str)
live = bool(token.strip())
banner = "🟢 实时数据" if live else "🟡 演示模式（填 Token 后自动切换实时）"
st.markdown(f"**{banner}** &nbsp;·&nbsp; 更新：{data['updatedAt']} &nbsp;·&nbsp; 说明：{data['note']}")

# ---- 主体：左待办 + 右四面板 ----
left, right = st.columns([1, 2.4])

# ---- 左：今日工作（可打勾） ----
with left:
    st.subheader("📝 今日工作")
    if "todos" not in st.session_state:
        st.session_state.todos = []
    new_t = st.text_input("添加一项工作", placeholder="例如：9:30 复盘美股盘前", key="new_todo")
    if st.button("➕ 添加", key="add_todo") and new_t.strip():
        st.session_state.todos.append({"text": new_t.strip(), "done": False})
        st.rerun()
    done = sum(1 for t in st.session_state.todos if t["done"])
    total = len(st.session_state.todos)
    if total:
        st.progress(done / total)
        st.caption(f"已完成 {done}/{total}")
    st.divider()
    for i, t in enumerate(st.session_state.todos):
        col1, col2 = st.columns([0.85, 0.15])
        checked = col1.checkbox(t["text"], value=t["done"], key=f"td_{i}")
        st.session_state.todos[i]["done"] = checked
        if col2.button("🗑", key=f"del_{i}"):
            st.session_state.todos.pop(i)
            st.rerun()

# ---- 右：四面板 ----
with right:
    # 面板1：美股速览 + 三大指数
    p1 = card("① 美股速览（三大板块 + 重点个股）",
              rows_html(data["usStocks"]["sectors"], val_fn=lambda x: pct(x["change"]))
              + '<div style="font-size:12px;color:#86909c;margin:8px 0 4px">重点个股</div>'
              + rows_html(data["usStocks"]["movers"], val_fn=lambda x: pct(x["change"])))
    p1 += card("美股三大指数", rows_html(data["usIndices"], val_fn=lambda x: pct(x["change"])))

    # 面板2：A股热话题
    p2 = rows_html(data["aTopics"], key_name="topic",
                   extra=lambda x: f'{x["board"]} · 热度 {x["heat"]}')
    p2 = card("② A股今日热话题", p2)

    # 面板3：日韩 14:00-15:00
    gov_html = '<div style="display:flex;flex-direction:column;gap:8px">'
    for g in data["jpKr"]["gov"]:
        gov_html += f'<div style="background:#f7f8fa;border-radius:8px;padding:8px 10px"><b>{g["h"]}</b><div style="font-size:12px;color:#86909c;margin-top:2px">{g["d"]}</div></div>'
    gov_html += "</div>"
    p3 = card("③ 日韩 14:00–15:00（政府/监管消息）", gov_html)
    p3 += card("日韩重点指数", rows_html(data["jpKr"]["stocks"], val_fn=lambda x: pct(x["change"])))

    # 面板4：A股 15:00 收盘
    flow_html = rows_html(data["aClose"]["sectors"],
                          extra=lambda x: f'流入 {net_amt(x["in"])} / 流出 {net_amt(x["out"])}')
    idx_html = rows_html(data["aClose"]["indices"], val_fn=lambda x: pct(x["change"]))
    nat_html = '<div style="display:flex;flex-direction:column;gap:8px">'
    for n in data["aClose"]["national"]:
        nat_html += f'<div style="background:#f7f8fa;border-radius:8px;padding:8px 10px"><b>{n["h"]}</b><div style="font-size:12px;color:#86909c;margin-top:2px">{n["d"]}</div></div>'
    nat_html += "</div>"
    p4 = card("④ A股 15:00 收盘 · 三大板块资金流（净流入/流出，亿元）", flow_html)
    p4 += card("主要指数涨跌", idx_html)
    p4 += card("国家层面资讯", nat_html)

    st.markdown(p1 + p2 + p3 + p4, unsafe_allow_html=True)
