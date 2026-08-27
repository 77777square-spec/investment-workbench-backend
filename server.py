#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投资顾问工作台 · 后端（纯标准库，无需 pip install 任何包）
功能：
  1. 打开 http://localhost:8000 即是工作台页面（本地用）
  2. /api/dashboard?token=你的TUSHARE_TOKEN&date=YYYY-MM-DD
     -> 用你填的 token 去 Tushare 拉 A股真实数据；
        -> 美股 / 日韩 / 板块资金流 走服务端直连（Yahoo / 东方财富），不受浏览器跨域限制
   - 任何一项拉不到，自动用演示数据补齐，页面照常可用
   - 部署到云端（如 Render）后，老师电脑无需装 Python，只要浏览器打开前端网址

运行：  python server.py
部署：  见 BACKEND_DEPLOY.md（Render 免费托管，约 3 分钟）
"""

import json
import os
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path

PORT = int(os.environ.get("PORT", 8000))
HERE = Path(__file__).resolve().parent
TS_API = "https://api.tushare.pro"
HTML_FILE = HERE / "investment-workbench.html"
if not HTML_FILE.exists():
    HTML_FILE = HERE / "dist" / "index.html"

# 演示数据兜底（仅在真实接口都拉不到时使用）
DEMO = {
    "usStocks": {
        "sectors": [{"name": "科技", "change": 1.82}, {"name": "金融", "change": -0.46}, {"name": "能源", "change": 0.93}],
        "movers": [        {"name": "英伟达 NVDA", "change": 3.21}, {"name": "苹果 AAPL", "change": -0.74},
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
                     {"h": "证监会：推进中长期资金入市", "d": "利好蓝筹估值"}]}
}


# ============== Tushare ==============
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


# ============== Yahoo Finance（美股 / 日韩，服务端并发拉取，短超时防卡死） ==============
import concurrent.futures
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def yahoo_change(symbol, timeout=3):
    """返回当日涨跌幅(%)；失败返回 None（query1/query2 各试一次，短超时）"""
    path = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=5d"
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            req = urllib.request.Request("https://" + host + path, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
            res = j["chart"]["result"][0]
            meta = res["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price and prev:
                return round((price - prev) / prev * 100, 2)
        except Exception as e:
            last_err = e
    return None


def _batch(sym_map, timeout=3):
    """sym_map: {symbol: name} -> {symbol: change_or_None} 并发拉取，防单点卡死"""
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
    out = []
    m = _batch({"^N225": "日经225", "^KS11": "韩国综指"})
    for sym, name in {"^N225": "日经225", "^KS11": "韩国综指"}.items():
        c = m.get(sym)
        if c is not None:
            out.append({"name": name, "change": c})
    return out



# ============== Tushare 全球指数（美股三大指数 / 日韩，服务端拉取，可靠） ==============
def fetch_global_indices(token, td, mapping):
    """mapping: {ts_code: 中文名}；返回 [{name, change}]"""
    out = []
    for code, name in mapping.items():
        d = ts_query(token, "index_global", {"ts_code": code, "trade_date": td}, "pct_chg")
        if d:
            for r in rows(d):
                if "pct_chg" in r:
                    out.append({"name": name, "change": float(r["pct_chg"])})
                    break
    return out


# ============== 东方财富：A股行业板块资金流（服务端直连） ==============
def fetch_sector_flow():
    """返回 [{name, net}]，net 为净流入(亿元)，正数=流入"""
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
            net = it.get("f62")  # 主力净流入(元)
            if name and net is not None:
                res.append({"name": name, "net": round(net / 1e8, 1)})
        return res[:8]
    except Exception as e:
        print(f"[warn] 东方财富板块资金流失败：{e}")
    return None


# ============== 组装看板 ==============
def build_dashboard(token, date_str):
    note = []
    td = date_str.replace("-", "") if date_str else datetime.now().strftime("%Y%m%d")

    # ---- 美股板块/个股（Yahoo 真实，尽力；失败回退演示） ----
    us_sec, us_mov = fetch_us()
    if us_sec and us_mov:
        us_stocks = {"sectors": us_sec, "movers": us_mov}
    else:
        us_stocks = DEMO["usStocks"]; note.append("美股板块/个股(演示)")

    # ---- 美股三大指数（Tushare index_global 真实） ----
    us_indices = fetch_global_indices(token, td, {"SPX": "标普500", "IXIC": "纳斯达克", "DJI": "道琼斯"})
    if not us_indices:
        us_indices = DEMO["usIndices"]; note.append("美股指数(演示)")

    # ---- A股三大指数（Tushare index_daily） ----
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

    # ---- 日韩指数（Tushare index_global 真实优先；Yahoo 兜底） ----
    asia_idx = fetch_global_indices(token, td, {"N225": "日经225", "KS11": "韩国综指"})
    if asia_idx:
        jpkr_stocks = asia_idx
    else:
        asia = fetch_asia()
        if asia:
            jpkr_stocks = asia
        else:
            jpkr_stocks = DEMO["jpKr"]["stocks"]; note.append("日韩(演示)")

    # ---- A股板块资金流（东方财富真实） ----
    flow = fetch_sector_flow()
    if flow:
        a_close_sectors = [{"name": s["name"],
                            "in": (s["net"] if s["net"] > 0 else 0),
                            "out": (-s["net"] if s["net"] < 0 else 0)} for s in flow]
    else:
        a_close_sectors = DEMO["aClose"]["sectors"]; note.append("资金流(演示)")

    # ---- 热话题 / 政策资讯：需大模型或新闻源，暂演示 ----
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


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if HTML_FILE.exists():
                body = HTML_FILE.read_bytes()
                self.send_response(200); self._cors()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404); self.end_headers()
            return

        if parsed.path.startswith("/api/dashboard"):
            q = urllib.parse.parse_qs(parsed.query)
            token = (q.get("token") or [""])[0].strip()
            date_str = (q.get("date") or [""])[0].strip()
            data = build_dashboard(token, date_str)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404); self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"✅ 工作台后端已启动：http://localhost:{PORT}")
    print("   （本地用：浏览器打开上面地址；部署用：见 BACKEND_DEPLOY.md）")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
