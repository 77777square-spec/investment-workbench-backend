# 后端部署指南（老师电脑无需装 Python）

老师只需要在浏览器里打开**前端工作台网址**即可使用。真正的行情数据由一个"后端"在云端计算，
老师这边完全不需要安装 Python。

真实数据链路：
- 美股三大指数 / 日经 / 韩国综指 → Tushare `index_global`（老师填自己的 token）
- A股三大指数 → Tushare `index_daily`
- A股板块资金流 → 东方财富（无需 token）
- 美股板块/个股 → Yahoo Finance（服务端拉取，不受浏览器跨域限制）

---

## 方式 A（推荐）：部署到 Render 免费托管（约 3 分钟，无需信用卡）

1. 把本仓库（含 `server.py` / `investment-workbench.html` / `requirements.txt` / `render.yaml`）推到你的 GitHub；
   或在本机 `git push` 已初始化的仓库。
2. 在 Render 新建 Web Service，选择刚推送的 GitHub 仓库：
   - Runtime: Python 3
   - Build Command: 留空（无需安装依赖，纯标准库）
   - Start Command: `python server.py`
   - 免费档（Free）即可
3. 部署完成后，Render 会给你一个网址，形如 `https://xxx.onrender.com`。
   **这个网址本身已经同时托管了工作台页面 + 数据接口（同源）**，所以老师不需要再填"服务地址"。
4. 老师打开 `https://xxx.onrender.com` → 点右上角「接入实时数据」→ **只粘贴自己的 32 位 Tushare Token** → 保存 → 刷新看板，
   即可看到实时行情。其他面板（美股板块/个股走 Yahoo、A股资金流走东方财富）会自动拉取。

> 也可继续用已部署的 CloudStudio 静态前端，在「接入实时数据」里把"服务地址"填成上面的 Render 网址、Token 填老师的，效果一样。
> 或把 CloudStudio 前端链接拼上参数直接下发：`https://你的前端网址?backend=https://xxx.onrender.com`

---

## 方式 B：学生本机运行 + 内网穿透（最快，无需注册）

1. 学生电脑（已装好 Python）运行：
   ```
   python server.py
   ```
2. 再用一条免费穿透命令把本机 8000 端口暴露为公网网址（任选其一）：
   - `ssh -R 80:localhost:8000 localhost.run` （回车后会打印一个公网网址）
   - 或使用 cloudflared / bore 等工具
3. 把得到的公网网址填到前端"服务地址"即可。
   注意：此方式依赖学生电脑在线；长期给老师用建议用方式 A。

---

## 方式 C：纯静态演示（已部署，零后端）

前端已部署到 CloudStudio，老师打开即是一个完整的工作台（每日待办可打勾 + 四块面板）。
未配置后端时显示"演示数据"，配置后端网址 + token 后即变为实时行情。
