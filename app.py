import io
import json
import os
import random
import time
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

try:
    from streamlit_javascript import st_javascript
except Exception:  # noqa: BLE001
    st_javascript = None

# ---------------- 基础配置 ----------------
st.set_page_config(page_title="投资顾问 AI 工作台", page_icon="📈", layout="wide")

TZ = ZoneInfo("Asia/Shanghai")
NOW = dt.datetime.now(TZ)
TODAY = NOW.date()

UP = "#ff5252"      # 涨 - 红（A股惯例）
DOWN = "#26de81"    # 跌 - 绿
FLAT = "#8b949e"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
}

PUSH2_MIRRORS = [f"{i}.push2.eastmoney.com" for i in (1, 2, 3, 4, 5, 6)] + ["push2.eastmoney.com"]

# 自适应传输通道：requests -> curl_cffi(浏览器TLS指纹) -> 系统curl
# （部分网络环境下东方财富会掐断 OpenSSL TLS 指纹的连接，系统 curl 可正常访问）
_TRANSPORT = {"mode": None}


def _via_requests(url, params, timeout):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    if r.status_code == 200 and r.text.strip():
        return r.json()
    return None


def _via_curl_cffi(url, params, timeout):
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, params=params, headers=HEADERS,
                   impersonate="chrome124", timeout=timeout)
        if r.status_code == 200 and r.text.strip():
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return None


def _via_syscurl(url, params, timeout):
    import subprocess
    import urllib.parse
    qs = urllib.parse.urlencode(params or {})
    full = url + ("?" + qs if qs else "")
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(int(timeout)),
             "-H", "User-Agent: " + HEADERS["User-Agent"],
             "-H", "Referer: " + HEADERS["Referer"], full],
            capture_output=True, text=True, timeout=timeout + 5)
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        pass
    return None


_TRANSPORTS = [
    ("requests", _via_requests),
    ("curl_cffi", _via_curl_cffi),
    ("syscurl", _via_syscurl),
]


# ---------------- 网络请求 ----------------
def http_get(url, params=None, tries=3, timeout=8):
    """多通道 + 镜像轮换 + 重试的 GET（东方财富 push2 对高频访问有限流）。"""
    last_err = None
    order = [t for t in _TRANSPORTS if t[0] == _TRANSPORT["mode"]] + \
            [t for t in _TRANSPORTS if t[0] != _TRANSPORT["mode"]]
    for i in range(tries):
        u = url
        if "push2.eastmoney.com" in u and i > 0:
            u = u.replace("push2.eastmoney.com", random.choice(PUSH2_MIRRORS))
        for name, fn in order:
            try:
                data = fn(u, params, timeout)
                if data:
                    _TRANSPORT["mode"] = name
                    return data
            except Exception as e:  # noqa: BLE001
                last_err = e
        time.sleep(0.4 * (i + 1))
    return None


def fmt_num(v, digits=2, dash="--"):
    if isinstance(v, (int, float)):
        return f"{v:,.{digits}f}"
    return dash


def fmt_pct(v, dash="--"):
    if isinstance(v, (int, float)):
        return f"{v:+.2f}%"
    return dash


def fmt_chg(v, dash="--"):
    if isinstance(v, (int, float)):
        return f"{v:+,.2f}"
    return dash


def cls_of(v):
    if not isinstance(v, (int, float)) or v == 0:
        return "flat"
    return "up" if v > 0 else "down"


def fmt_yi(v, signed=True, dash="--"):
    """元 -> 亿元"""
    if isinstance(v, (int, float)):
        s = f"{v / 1e8:,.2f}"
        if signed:
            s = ("+" if v >= 0 else "-") + s
        return s + " 亿"
    return dash


def colorize(text, cls):
    return f'<span class="{cls}">{text}</span>'


# ---------------- 数据接口（全部来自东方财富） ----------------
SEC_CN = "1.000001,0.399001,0.399006"          # 上证 / 深证 / 创业板
SEC_US = "100.DJIA,100.SPX,100.NDX"             # 道琼斯 / 标普500 / 纳斯达克
SEC_JPKR = "100.N225,100.KS11"                  # 日经225 / 韩国KOSPI
US_WATCH = [
    ("105", "AAPL"), ("105", "MSFT"), ("105", "NVDA"), ("105", "GOOG"),
    ("105", "AMZN"), ("105", "META"), ("105", "TSLA"), ("105", "AMD"),
    ("106", "BA"), ("106", "JPM"), ("106", "KO"), ("106", "DIS"),
]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_quotes(secids):
    d = http_get("https://push2.eastmoney.com/api/qt/ulist.np/get",
                 {"fltt": 2, "invt": 2, "fields": "f2,f3,f4,f6,f12,f13,f14", "secids": secids})
    out = {}
    if d and d.get("data"):
        for x in d["data"].get("diff", []):
            out[x["f12"]] = x
    return out


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_indices():
    """一次性拉取全部指数（美股三大 + A股三大 + 日韩），减少请求次数"""
    return fetch_quotes(",".join([SEC_US, SEC_CN, SEC_JPKR]))


@st.cache_data(ttl=60, show_spinner=False)
def fetch_sector_rank(kind="industry", top=10):
    """板块涨幅榜：kind=industry 行业 / concept 概念"""
    fs = "m:90+t:2" if kind == "industry" else "m:90+t:3"
    d = http_get("https://push2.eastmoney.com/api/qt/clist/get",
                 {"fid": "f3", "po": 1, "pz": top, "pn": 1, "np": 1, "fltt": 2,
                  "invt": 2, "fs": fs, "fields": "f12,f14,f3,f128,f140,f136"})
    if not d or not d.get("data"):
        return []
    rows = []
    for x in d["data"].get("diff", []):
        rows.append({
            "name": x.get("f14"), "pct": x.get("f3"),
            "leader": x.get("f128"), "leader_pct": x.get("f140"),
        })
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def fetch_sector_flow(direction="in", top=10):
    """行业板块主力资金流：direction=in 净流入榜 / out 净流出榜"""
    d = http_get("https://push2.eastmoney.com/api/qt/clist/get",
                 {"fid": "f62", "po": 1 if direction == "in" else 0, "pz": top,
                  "pn": 1, "np": 1, "fltt": 2, "invt": 2, "fs": "m:90+t:2",
                  "fields": "f12,f14,f3,f62,f184,f204"})
    if not d or not d.get("data"):
        return []
    rows = []
    for x in d["data"].get("diff", []):
        rows.append({
            "name": x.get("f14"), "pct": x.get("f3"),
            "flow": x.get("f62"), "ratio": x.get("f184"), "leader": x.get("f204"),
        })
    return rows


@st.cache_data(ttl=120, show_spinner=False)
def fetch_zdt_pool(kind="zt"):
    """涨停池 / 跌停池，非交易日自动回溯最近交易日"""
    base = TODAY
    for back in range(6):
        date = (base - dt.timedelta(days=back)).strftime("%Y%m%d")
        if kind == "zt":
            url = "https://push2ex.eastmoney.com/getTopicZTPool"
            params = {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                      "Pageindex": 0, "pagesize": 1000, "sort": "fbt:asc", "date": date}
        else:
            url = "https://push2ex.eastmoney.com/getTopicDTPool"
            params = {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                      "Pageindex": 0, "pagesize": 1000, "sort": "fund:asc", "date": date}
        d = http_get(url, params)
        if d and d.get("data") and d["data"].get("pool"):
            pool = d["data"]["pool"]
            return {"date": date, "count": d["data"].get("tc", len(pool)), "pool": pool}
        if d and d.get("data") and d["data"].get("tc", 0) == 0 and d["data"].get("pool") == []:
            # 当日确无涨停/跌停
            return {"date": date, "count": 0, "pool": []}
    return {"date": None, "count": 0, "pool": []}


@st.cache_data(ttl=120, show_spinner=False)
def fetch_fenbu():
    """全市场涨跌分布（家数）"""
    d = http_get("https://push2ex.eastmoney.com/getTopicZDFenBu",
                 {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt"})
    if not d or not d.get("data"):
        return None
    up = down = flat = 0
    for item in d["data"].get("fenbu", []):
        for k, v in item.items():
            k = int(k)
            if k > 0:
                up += v
            elif k < 0:
                down += v
            else:
                flat += v
    return {"up": up, "down": down, "flat": flat}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_news():
    """东方财富 7x24 全球快讯"""
    try:
        r = requests.get(
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
            params={"client": "web", "biz": "web_724", "fastColumn": "102",
                    "sortEnd": "", "pageSize": 50, "req_trace": str(int(time.time() * 1000))},
            headers=HEADERS, timeout=10)
        items = (r.json().get("data") or {}).get("fastNewsList") or []
        return [{"time": (x.get("showTime") or "")[11:16],
                 "title": x.get("title", "").strip(),
                 "summary": (x.get("summary") or "").strip()} for x in items]
    except Exception:  # noqa: BLE001
        return []


def filter_news(news, keywords, limit=8):
    seen, out = set(), []
    for n in news:
        text = n["title"] + n["summary"]
        if any(k in text for k in keywords):
            if n["title"] not in seen:
                seen.add(n["title"])
                out.append(n)
        if len(out) >= limit:
            break
    return out


NEWS_KW_US = ["美股", "纳斯达克", "标普", "道琼斯", "美联储", "鲍威尔", "华尔街",
              "美国经济", "美股财报", "科技股", "英伟达", "特斯拉", "苹果"]
NEWS_KW_JPKR = ["日本", "日经", "日元", "日央行", "日本央行", "东京", "安倍", "石破",
                "韩国", "韩元", "韩国央行", "KOSPI", "首尔", "三星", "现代", "SK海力士",
                "日本政府", "韩国政府", "日本内阁"]
NEWS_KW_CN_GOV = ["国务院", "央行", "中国人民银行", "证监会", "财政部", "发改委",
                  "商务部", "工信部", "国家统计局", "政策", "国常会", "中央",
                  "降准", "降息", "LPR", "关税", "反制"]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_hot_rank(top=10):
    """东方财富 A股人气榜"""
    try:
        r = requests.post(
            "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
                  "marketType": "", "pageNo": 1, "pageSize": top},
            headers=HEADERS, timeout=10)
        data = r.json().get("data") or []
        secids = ",".join(
            ("1." if x["sc"].startswith("SH") else "0.") + x["sc"][2:] for x in data)
        quotes = fetch_quotes(secids)
        rows = []
        for x in data:
            code = x["sc"][2:]
            q = quotes.get(code, {})
            rows.append({
                "rank": x.get("rk"), "name": q.get("f14", code),
                "code": code, "pct": q.get("f3"), "chg": x.get("rc"),
            })
        return rows
    except Exception:  # noqa: BLE001
        return []


# ---------------- 待办事项（浏览器 localStorage 持久化，刷新/重启不丢） ----------------
LS_KEY = "teacher_todos_v1"
TODO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todos.json")
DEFAULT_TODOS = [
    {"text": "查看隔夜美股三大指数与重点个股", "done": False},
    {"text": "梳理今日 A 股热门话题与人气榜", "done": False},
    {"text": "14:00 关注日韩市场与政府消息", "done": False},
    {"text": "15:00 A 股收盘复盘：资金流向与国家资讯", "done": False},
]


def load_todos_from_ls():
    """从浏览器 localStorage 读取待办（仅首次初始化时调用）。"""
    if st_javascript is None:
        return None
    try:
        raw = st_javascript(f"localStorage.getItem('{LS_KEY}')")
        if isinstance(raw, str) and raw.strip():
            return json.loads(raw)
    except Exception:  # noqa: BLE001
        pass
    return None


def sync_todos():
    """把当前待办写回浏览器 localStorage（同时落一份本地文件做备份）。

    写入用 st_javascript 注入到主页面执行，避免使用 components.html
    （该接口在新版 Streamlit 中已被移除）。
    """
    items = st.session_state.get("todos", [])
    if st_javascript is not None:
        try:
            st_javascript(
                f"localStorage.setItem('{LS_KEY}', JSON.stringify("
                f"{json.dumps(items, ensure_ascii=False)}));")
        except Exception:  # noqa: BLE001
            pass
    try:
        with open(TODO_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


# ---------------- 渲染组件 ----------------
def inject_css():
    st.markdown("""
<style>
  /* 强制深色背景：即使 .streamlit/config.toml 未生效也不变成浅色 */
  .stApp {background: #0e1117 !important; color: #e6edf3 !important;}
  header[data-testid="stHeader"] {background: rgba(14,17,23,.9) !important;}
  div[data-testid="stTabs"] button {color: #c9d1d9 !important;}
  div[data-testid="stTabs"] button[aria-selected="true"] {color: #ffd76e !important; border-bottom: 2px solid #ffd76e !important;}
  .stTextInput>div>div>input {background: #161b22 !important; color: #e6edf3 !important; border: 1px solid #30363d !important;}

  .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px;}
  div[data-testid="stMarkdown"] p {margin-bottom: 0;}
  .up   {color: #ff5252; font-weight: 600;}
  .down {color: #26de81; font-weight: 600;}
  .flat {color: #8b949e;}

  .app-header {display:flex; align-items:center; justify-content:space-between;
               flex-wrap:wrap; gap:10px; margin-bottom:6px;}
  .app-title {font-size:1.7rem; font-weight:800; letter-spacing:1px;
              background:linear-gradient(90deg,#ffd76e,#ff8a5c);
              -webkit-background-clip:text; background-clip:text; color:transparent;}
  .app-sub {color:#8b949e; font-size:.85rem;}
  .badge {display:inline-block; padding:3px 12px; border-radius:999px; font-size:.78rem;
          border:1px solid #30363d; color:#c9d1d9; background:#161b22;}

  .grid {display:grid; gap:14px; margin:10px 0 4px;}
  .grid.c3 {grid-template-columns:repeat(3, 1fr);}
  .grid.c4 {grid-template-columns:repeat(4, 1fr);}
  @media (max-width: 900px){ .grid.c3,.grid.c4 {grid-template-columns:repeat(2,1fr);} }

  .card {background:linear-gradient(160deg,#171c24 0%,#10141a 100%);
         border:1px solid #232a33; border-radius:14px; padding:16px 18px;}
  .card .k {color:#8b949e; font-size:.8rem; margin-bottom:6px;}
  .card .v {font-size:1.45rem; font-weight:750;}
  .card .s {font-size:.8rem; color:#8b949e; margin-top:5px;}

  .callout {border-left:4px solid #ffd76e; background:rgba(255,215,110,.07);
            border-radius:8px; padding:12px 16px; margin:10px 0 16px;
            font-size:.98rem; line-height:1.75; color:#e6edf3;}
  .callout b {color:#ffd76e;}

  .tbl {width:100%; border-collapse:collapse; font-size:.88rem; margin-top:6px;}
  .tbl th {text-align:left; color:#8b949e; font-weight:600; font-size:.78rem;
           padding:7px 10px; border-bottom:1px solid #30363d; white-space:nowrap;}
  .tbl td {padding:8px 10px; border-bottom:1px solid #21262d; color:#e6edf3;}
  .tbl tr:last-child td {border-bottom:none;}
  .tbl .num {text-align:right; font-variant-numeric:tabular-nums;}

  .news-item {display:flex; gap:10px; padding:8px 4px; border-bottom:1px dashed #21262d;
              align-items:baseline;}
  .news-time {color:#ffd76e; font-size:.75rem; font-family:Consolas,monospace;
              flex:0 0 44px;}
  .news-title {color:#e6edf3; font-size:.88rem; line-height:1.55;}

  .sec-title {display:flex; align-items:center; gap:8px; margin:18px 0 8px;
              font-size:1.05rem; font-weight:700; color:#e6edf3;}
  .sec-title .bar {width:4px; height:18px; border-radius:2px;
                   background:linear-gradient(180deg,#ffd76e,#ff8a5c);}
  .sec-title .hint {font-size:.75rem; color:#8b949e; font-weight:400; margin-left:6px;}

  .rank-pill {display:inline-block; min-width:22px; text-align:center; padding:2px 7px;
              border-radius:6px; font-size:.75rem; background:#21262d; color:#c9d1d9;}
  .rank-pill.top1 {background:rgba(255,82,82,.18); color:#ff8a80;}
  .done-text {text-decoration:line-through; color:#8b949e;}
  .footer-note {color:#58606a; font-size:.75rem; text-align:center; margin-top:28px;}
</style>""", unsafe_allow_html=True)


def index_card(name, price, pct, chg, sub=""):
    c = cls_of(pct)
    arrow = "▲" if c == "up" else ("▼" if c == "down" else "●")
    chg_html = f"{arrow} {fmt_chg(chg)}" if chg != "--" else ""
    sub_html = f'<div class="s">{sub}</div>' if sub else ""
    return f"""
<div class="card">
  <div class="k">{name}</div>
  <div class="v {c}">{fmt_num(price)}</div>
  <div class="s {c}" style="font-size:.95rem;">{fmt_pct(pct)} &nbsp;{chg_html}</div>
  {sub_html}
</div>"""


def simple_card(label, value_html, sub=""):
    sub_html = f'<div class="s">{sub}</div>' if sub else ""
    return f"""
<div class="card">
  <div class="k">{label}</div>
  <div class="v">{value_html}</div>
  {sub_html}
</div>"""


def html_table(headers, rows, num_cols=()):
    """rows: 二维数组，元素为已格式化的 HTML 字符串"""
    th = "".join(
        f'<th class="{"num" if i in num_cols else ""}">{h}</th>'
        for i, h in enumerate(headers))
    trs = []
    for r in rows:
        tds = "".join(
            f'<td class="{"num" if i in num_cols else ""}">{v}</td>'
            for i, v in enumerate(r))
        trs.append(f"<tr>{tds}</tr>")
    return f'<table class="tbl"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


def sec_title(text, hint=""):
    h = f'<span class="hint">{hint}</span>' if hint else ""
    return f'<div class="sec-title"><span class="bar"></span>{text}{h}</div>'


def news_list(news):
    if not news:
        return '<div class="news-title" style="color:#8b949e;">暂无相关资讯，请稍后刷新。</div>'
    items = "".join(
        f'<div class="news-item"><span class="news-time">{n["time"]}</span>'
        f'<span class="news-title">{n["title"]}</span></div>'
        for n in news)
    return f'<div>{items}</div>'


def market_phase(now):
    h, wd = now.time(), now.weekday()
    if wd >= 5:
        return "周末休市 · 可复盘本周数据", "#8b949e"
    if h < dt.time(9, 15):
        return "盘前 · 建议先看隔夜美股速览", "#58a6ff"
    if h < dt.time(11, 30):
        return "A股早盘 · 关注热点与人气榜", "#26de81"
    if h < dt.time(13, 0):
        return "午间休市", "#8b949e"
    if h < dt.time(14, 0):
        return "A股午后 · 留意日韩市场联动", "#26de81"
    if h < dt.time(15, 0):
        return "尾盘 · 14:00-15:00 关注日韩市场动态", "#ffd76e"
    return "已收盘 · 15:00 后做盘后复盘", "#ff8a5c"


# ---------------- 页面 ----------------
def main():
    inject_css()

    phase, phase_color = market_phase(NOW)
    wk = "一二三四五六日"[NOW.weekday()]

    left, right = st.columns([5, 2])
    with left:
        st.markdown(
            f'<div class="app-header"><div>'
            f'<div class="app-title">📈 投资顾问 AI 工作台</div>'
            f'<div class="app-sub">{NOW.year} 年 {NOW.month} 月 {NOW.day} 日 · 星期{wk} · '
            f'数据来源：东方财富</div></div></div>', unsafe_allow_html=True)
    with right:
        st.markdown(
            f'<div style="text-align:right; margin:6px 0 10px;">'
            f'<span class="badge" style="border-color:{phase_color}55; color:{phase_color};">'
            f'⏱ {phase}</span></div>', unsafe_allow_html=True)
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    tab_us, tab_hot, tab_jpkr, tab_close, tab_todo = st.tabs(
        ["🌙 隔夜美股", "🔥 A股热点", "🌏 日韩市场", "📊 A股盘后复盘", "✅ 今日待办"])

    # ============ Tab 1: 隔夜美股 ============
    with tab_us:
        us = fetch_all_indices()
        if us:
            names = {"DJIA": "道琼斯", "SPX": "标普500", "NDX": "纳斯达克"}
            cards = []
            for code, nm in names.items():
                q = us.get(code, {})
                cards.append(index_card(nm, q.get("f2"), q.get("f3"), q.get("f4")))
            st.markdown(f'<div class="grid c3">{"".join(cards)}</div>', unsafe_allow_html=True)

            pcts = {c: us.get(c, {}).get("f3") for c in names}
            valid = [p for p in pcts.values() if isinstance(p, (int, float))]
            if valid:
                if all(p > 0 for p in valid):
                    tone = "三大指数<b>集体收涨</b>"
                elif all(p < 0 for p in valid):
                    tone = "三大指数<b>集体收跌</b>"
                else:
                    tone = "三大指数<b>涨跌互现</b>"
                best = max(names, key=lambda c: (pcts.get(c) or 0))
                worst = min(names, key=lambda c: (pcts.get(c) or 0))
                st.markdown(
                    f'<div class="callout">隔夜美股：{tone}。'
                    f'领涨 {names.get(best)} <b>{fmt_pct(pcts.get(best))}</b>，'
                    f'表现最弱 {names.get(worst)} {fmt_pct(pcts.get(worst))}。'
                    f"重点关注科技股与美联储动态对今日 A 股开盘情绪的影响。</div>",
                    unsafe_allow_html=True)
        else:
            st.info("指数数据暂时获取失败（东方财富接口限流），请稍后点击右上角「刷新数据」重试。")

        st.markdown(sec_title("重点个股观察", "可自定义自选股代码"), unsafe_allow_html=True)
        custom = st.text_input(
            "美股自选（市场代码.代码，逗号分隔。105=纳斯达克，106=纽交所）",
            value=",".join(f"{m}.{c}" for m, c in US_WATCH),
            help="例如：105.AAPL,105.NVDA,106.BA。修改后点击页面任意刷新即可生效。")
        secids = ",".join(x.strip() for x in custom.split(",") if x.strip()) or \
            ",".join(f"{m}.{c}" for m, c in US_WATCH)
        stocks = fetch_quotes(secids)
        if stocks:
            rows = []
            order = [s.strip() for s in secids.split(",")]
            for s in order:
                code = s.split(".")[-1]
                q = stocks.get(code)
                if not q:
                    continue
                c = cls_of(q.get("f3"))
                rows.append([
                    q.get("f14", code), code,
                    colorize(fmt_num(q.get("f2")), c),
                    colorize(fmt_pct(q.get("f3")), c),
                    colorize(fmt_chg(q.get("f4")), c),
                ])
            st.markdown(html_table(
                ["名称", "代码", "最新价", "涨跌幅", "涨跌额"], rows, num_cols=(2, 3, 4)),
                unsafe_allow_html=True)

        st.markdown(sec_title("美股相关资讯", "东方财富 7x24 快讯 · 自动筛选"), unsafe_allow_html=True)
        st.markdown(news_list(filter_news(fetch_news(), NEWS_KW_US)), unsafe_allow_html=True)

    # ============ Tab 2: A股热点 ============
    with tab_hot:
        fenbu = fetch_fenbu()
        zt = fetch_zdt_pool("zt")
        if fenbu:
            ratio = fenbu["up"] / max(fenbu["up"] + fenbu["down"], 1)
            if ratio > 0.65:
                mood = "普涨，赚钱效应较好"
            elif ratio > 0.5:
                mood = "偏强"
            elif ratio > 0.4:
                mood = "涨跌互现"
            elif ratio > 0.3:
                mood = "偏弱"
            else:
                mood = "普跌，亏钱效应明显"
            st.markdown(
                f'<div class="callout">今日盘面：上涨 <b>{fenbu["up"]:,}</b> 家 / '
                f'下跌 <b>{fenbu["down"]:,}</b> 家，{mood}；'
                f'涨停 <b>{zt["count"]}</b> 家，最高连板 <b>'
                f'{max((p.get("lbc", 0) for p in zt["pool"]), default=0)}</b> 板。</div>',
                unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(sec_title("概念板块涨幅 TOP10"), unsafe_allow_html=True)
            rows = []
            for i, r in enumerate(fetch_sector_rank("concept", 10), 1):
                c = cls_of(r["pct"])
                rows.append([
                    f'<span class="rank-pill{" top1" if i == 1 else ""}">{i}</span>',
                    r["name"], colorize(fmt_pct(r["pct"]), c),
                    r.get("leader") or "--",
                    colorize(fmt_pct(r.get("leader_pct")), cls_of(r.get("leader_pct"))),
                ])
            st.markdown(html_table(
                ["#", "概念板块", "涨幅", "领涨股", "领涨股涨幅"], rows, num_cols=(2, 4)),
                unsafe_allow_html=True)
        with c2:
            st.markdown(sec_title("行业板块涨幅 TOP10"), unsafe_allow_html=True)
            rows = []
            for i, r in enumerate(fetch_sector_rank("industry", 10), 1):
                c = cls_of(r["pct"])
                rows.append([
                    f'<span class="rank-pill{" top1" if i == 1 else ""}">{i}</span>',
                    r["name"], colorize(fmt_pct(r["pct"]), c),
                    r.get("leader") or "--",
                    colorize(fmt_pct(r.get("leader_pct")), cls_of(r.get("leader_pct"))),
                ])
            st.markdown(html_table(
                ["#", "行业板块", "涨幅", "领涨股", "领涨股涨幅"], rows, num_cols=(2, 4)),
                unsafe_allow_html=True)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown(sec_title("个股人气榜 TOP10", "东方财富 A股人气排行"), unsafe_allow_html=True)
            rows = []
            for r in fetch_hot_rank(10):
                c = cls_of(r.get("pct"))
                rows.append([
                    f'<span class="rank-pill{" top1" if r["rank"] == 1 else ""}">{r["rank"]}</span>',
                    r["name"], r["code"],
                    colorize(fmt_pct(r.get("pct")), c),
                ])
            st.markdown(html_table(["人气排名", "股票", "代码", "涨跌幅"], rows, num_cols=(3,)),
                        unsafe_allow_html=True)
        with c4:
            st.markdown(sec_title("涨停梯队", "按连板数排序 · 简版"), unsafe_allow_html=True)
            pool = sorted(zt.get("pool", []), key=lambda p: -(p.get("lbc") or 0))[:10]
            rows = []
            for p in pool:
                lb = p.get("lbc") or 1
                zttj = p.get("zttj") or {}
                rows.append([
                    colorize(f"{lb} 板", "up"),
                    p.get("n", ""), p.get("c", ""),
                    p.get("hybk", ""),
                    f'{zttj.get("days", lb)}天{zttj.get("ct", lb)}板' if zttj else "--",
                ])
            if rows:
                st.markdown(html_table(
                    ["连板", "股票", "代码", "所属板块", "涨停记录"], rows, num_cols=(4,)),
                    unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#8b949e;font-size:.85rem;">'
                            '暂无涨停数据（非交易日或数据未生成）。</div>',
                            unsafe_allow_html=True)

    # ============ Tab 3: 日韩市场 ============
    with tab_jpkr:
        jk = fetch_all_indices()
        if jk:
            cards = [
                index_card("日经225", jk.get("N225", {}).get("f2"),
                           jk.get("N225", {}).get("f3"), jk.get("N225", {}).get("f4"),
                           sub="日本 · 东京证券交易所"),
                index_card("韩国 KOSPI", jk.get("KS11", {}).get("f2"),
                           jk.get("KS11", {}).get("f3"), jk.get("KS11", {}).get("f4"),
                           sub="韩国 · 首尔证券交易所"),
            ]
            st.markdown(f'<div class="grid c2" '
                        f'style="display:grid;grid-template-columns:repeat(2,1fr);gap:14px;'
                        f'margin:10px 0 4px;">{"".join(cards)}</div>', unsafe_allow_html=True)
            n = jk.get("N225", {}).get("f3")
            k = jk.get("KS11", {}).get("f3")
            if isinstance(n, (int, float)) and isinstance(k, (int, float)):
                tone = ("日韩市场集体走强" if n > 0 and k > 0 else
                        "日韩市场集体走弱" if n < 0 and k < 0 else "日韩市场涨跌互现")
                st.markdown(
                    f'<div class="callout">亚太时段：{tone}。日经225 {fmt_pct(n)}，'
                    f'KOSPI {fmt_pct(k)}。14:00-15:00 重点关注两国政府政策动向、'
                    f"半导体/汽车等核心产业股表现，以及对 A 股尾盘的联动影响。</div>",
                    unsafe_allow_html=True)
        else:
            st.info("日韩指数数据暂时获取失败（东方财富接口限流），请稍后点击右上角「刷新数据」重试。")

        st.markdown(sec_title("日韩市场资讯", "政府消息 · 央行动态 · 重要个股"),
                    unsafe_allow_html=True)
        st.markdown(news_list(filter_news(fetch_news(), NEWS_KW_JPKR, limit=10)),
                    unsafe_allow_html=True)

    # ============ Tab 4: A股盘后复盘（参考盘后复盘 PDF · 简化版） ============
    with tab_close:
        cn = fetch_all_indices()
        fenbu = fetch_fenbu()
        zt = fetch_zdt_pool("zt")
        dt_pool = fetch_zdt_pool("dt")

        # 指数卡片
        if cn:
            names = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指"}
            cards = []
            for code, nm in names.items():
                q = cn.get(code, {})
                amt = q.get("f6")
                sub = f"成交 {fmt_yi(amt, signed=False)}" if isinstance(amt, (int, float)) else ""
                cards.append(index_card(nm, q.get("f2"), q.get("f3"), q.get("f4"), sub=sub))
            total_amt = sum(cn.get(c, {}).get("f6") or 0 for c in names)
            cards.append(simple_card(
                "两市成交（沪+深）",
                f'<span style="color:#ffd76e;">{fmt_yi(total_amt, signed=False)}</span>',
                sub="数据实时更新"))
            st.markdown(f'<div class="grid c4">{"".join(cards)}</div>', unsafe_allow_html=True)
        else:
            st.info("指数数据暂时获取失败（东方财富接口限流），请稍后点击右上角「刷新数据」重试。")

        # 结论先行
        if fenbu:
            ratio = fenbu["up"] / max(fenbu["up"] + fenbu["down"], 1)
            if ratio > 0.65:
                mood = "普涨，赚钱效应较好"
            elif ratio > 0.5:
                mood = "偏强"
            elif ratio > 0.4:
                mood = "涨跌互现"
            elif ratio > 0.3:
                mood = "偏弱"
            else:
                mood = "普跌，亏钱效应明显"
            idx_desc = "、".join(
                f'{cn.get(c, {}).get("f14", "")} {fmt_pct(cn.get(c, {}).get("f3"))}'
                for c in ("000001", "399001", "399006") if cn.get(c)) or "指数数据获取失败"
            flow_in = fetch_sector_flow("in", 1)
            flow_out = fetch_sector_flow("out", 1)
            fin = flow_in[0]["name"] if flow_in else "--"
            fout = flow_out[0]["name"] if flow_out else "--"
            st.markdown(
                f'<div class="callout"><b>结论先行：</b>{idx_desc}；'
                f'上涨 <b>{fenbu["up"]:,}</b> 家 / 下跌 <b>{fenbu["down"]:,}</b> 家，{mood}；'
                f'涨停 <b>{zt["count"]}</b> 家、跌停 <b>{dt_pool["count"]}</b> 家；'
                f"主力资金净流入居前：<b>{fin}</b>，流出居前：<b>{fout}</b>。</div>",
                unsafe_allow_html=True)

        # 涨跌结构
        st.markdown(sec_title("涨跌结构", "全市场情绪概览"), unsafe_allow_html=True)
        if fenbu:
            max_lb = max((p.get("lbc") or 0) for p in zt.get("pool", [])) if zt.get("pool") else 0
            cells = [
                simple_card("上涨家数", colorize(f'{fenbu["up"]:,}', "up")),
                simple_card("下跌家数", colorize(f'{fenbu["down"]:,}', "down")),
                simple_card("平盘家数", f'<span class="flat">{fenbu["flat"]:,}</span>'),
                simple_card("涨停 / 跌停",
                            f'<span class="up">{zt["count"]}</span>'
                            f'&nbsp;/&nbsp;<span class="down">{dt_pool["count"]}</span>',
                            sub=f"最高连板 {max_lb} 板" if max_lb else ""),
            ]
            st.markdown(f'<div class="grid c4">{"".join(cells)}</div>', unsafe_allow_html=True)

        # 资金流向双表
        st.markdown(sec_title("主力资金流向 · 行业板块", "净流入 / 净流出 TOP10"),
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            rows = []
            for r in fetch_sector_flow("in", 10):
                c = cls_of(r["pct"])
                rows.append([r["name"], colorize(fmt_pct(r["pct"]), c),
                             colorize(fmt_yi(r["flow"]), "up"),
                             r.get("leader") or "--"])
            st.markdown(
                f'<div style="font-size:.85rem;color:#26de81;font-weight:600;'
                f'margin-bottom:2px;">流入榜</div>'
                + (html_table(["板块", "涨幅", "主力净流入", "领涨股"], rows, num_cols=(1, 2))
                   if rows else '<div style="color:#8b949e;font-size:.85rem;">数据暂不可用，请刷新重试。</div>'),
                unsafe_allow_html=True)
        with c2:
            rows = []
            for r in fetch_sector_flow("out", 10):
                c = cls_of(r["pct"])
                rows.append([r["name"], colorize(fmt_pct(r["pct"]), c),
                             colorize(fmt_yi(r["flow"]), "down"),
                             r.get("leader") or "--"])
            st.markdown(
                f'<div style="font-size:.85rem;color:#ff5252;font-weight:600;'
                f'margin-bottom:2px;">流出榜</div>'
                + (html_table(["板块", "涨幅", "主力净流出", "领涨股"], rows, num_cols=(1, 2))
                   if rows else '<div style="color:#8b949e;font-size:.85rem;">数据暂不可用，请刷新重试。</div>'),
                unsafe_allow_html=True)

        # 国家层面资讯
        st.markdown(sec_title("国家层面资讯", "政策 · 部委 · 宏观"),
                    unsafe_allow_html=True)
        st.markdown(news_list(filter_news(fetch_news(), NEWS_KW_CN_GOV, limit=10)),
                    unsafe_allow_html=True)

    # ============ Tab 5: 今日待办 ============
    with tab_todo:
        if "todos" not in st.session_state:
            ls = load_todos_from_ls()
            st.session_state.todos = ls if ls else [dict(x) for x in DEFAULT_TODOS]

        st.markdown(
            '<div class="callout">每天的工作清单。勾选完成事项，次日自动重置为默认工作流。'
            "可以自由添加 / 删除。</div>", unsafe_allow_html=True)

        col_in, col_btn = st.columns([5, 1])
        with col_in:
            new_item = st.text_input("新增待办", placeholder="输入待办事项后点击右侧按钮添加",
                                     label_visibility="collapsed")
        with col_btn:
            if st.button("➕ 添加", use_container_width=True):
                if new_item.strip():
                    st.session_state.todos.append({"text": new_item.strip(), "done": False})
                    sync_todos()
                    st.rerun()

        done_cnt = sum(1 for t in st.session_state.todos if t["done"])
        total = len(st.session_state.todos)
        st.progress(done_cnt / total if total else 0)
        st.caption(f"已完成 {done_cnt} / {total}")

        for i, todo in enumerate(st.session_state.todos):
            row1, row2, row3 = st.columns([0.6, 10, 0.8])
            with row1:
                checked = st.checkbox("done", value=todo["done"], key=f"todo_ck_{i}",
                                      label_visibility="collapsed")
                if checked != todo["done"]:
                    st.session_state.todos[i]["done"] = checked
                    sync_todos()
                    st.rerun()
            with row2:
                if todo["done"]:
                    st.markdown(f'<span class="done-text" style="font-size:.95rem;">'
                                f'✔ {todo["text"]}</span>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span style="font-size:.95rem;color:#e6edf3;">'
                                f'○ {todo["text"]}</span>', unsafe_allow_html=True)
            with row3:
                if st.button("🗑", key=f"del_{i}", help="删除该条"):
                    st.session_state.todos.pop(i)
                    sync_todos()
                    st.rerun()

        st.divider()
        cc1, cc2, _ = st.columns([1, 1, 2])
        with cc1:
            if st.button("清除已完成", use_container_width=True):
                st.session_state.todos = [t for t in st.session_state.todos if not t["done"]]
                sync_todos()
                st.rerun()
        with cc2:
            if st.button("重置为默认清单", use_container_width=True):
                st.session_state.todos = [dict(x) for x in DEFAULT_TODOS]
                sync_todos()
                st.rerun()

        # 每次渲染结束同步一次到浏览器 localStorage（持久化，刷新/重启不丢）
        sync_todos()

    st.markdown(
        '<div class="footer-note">数据来源：东方财富（push2 / 7x24 快讯 / 人气榜接口）· '
        "行情与资讯仅供工作参考，不构成投资建议</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
