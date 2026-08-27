# 部署指南（老师电脑无需装 Python）

老师只需要在浏览器里打开**工作台网址**即可使用。真正的行情数据由一个"后端"在云端计算，
老师这边完全不需要安装 Python。老师填的 Tushare Token 只存在他自己的浏览器里，不会上传到任何服务器。

真实数据链路：
- 美股三大指数 / 日经 / 韩国综指 → Tushare `index_global`（老师填自己的 token）
- A股三大指数 → Tushare `index_daily`
- A股板块资金流 → 东方财富（无需 token）
- 美股板块/个股 → Yahoo Finance（服务端拉取，不受浏览器跨域限制）
- 热话题 / 政策资讯：暂为演示位，需接大模型或新闻源

> ⚠️ 老师填的 Tushare Token 必须是 **tushare.pro 个人中心复制的 32 位**字符，不是随便敲的串。

---

## ✅ 推荐方案（免信用卡）：Streamlit Community Cloud

完全免费、**无需绑定信用卡**、纯 Python、后端能正常访问外网拉数据。一个 `app.py` 同时承载
界面 + 数据，老师打开就是一个完整工作台（含可打勾待办 + 四块面板）。

1. 本仓库已推到 GitHub：`https://github.com/77777square-spec/investment-workbench-backend`
   （你也可以用自己账号新建仓库，把 `app.py` + `requirements.txt` 传上去）
2. 打开 **https://share.streamlit.io** → 用 GitHub 登录
3. 点 **Create app / New app**
   - Repository：`77777square-spec/investment-workbench-backend`
   - Branch：`main`
   - Main file path：`app.py`
   - 其它默认
4. 点 **Deploy!**
5. 等 1–2 分钟构建完成，得到一个网址，形如：
   `https://你的账号-investment-workbench-backend.streamlit.app`
6. 老师打开该网址 → 左侧「⚙️ 设置」→ **粘贴自己的 32 位 Tushare Token** → 选日期 → 刷新，
   即看实时行情（不填则显示演示数据）

> 免费档说明：长时间无人访问会自动休眠，首次打开约等 10–30 秒唤醒，正常。
> 资源约 1 核 CPU / 1GB 内存，够用。仓库需为**公开**（免费档要求）。

---

## 其他方案（备查）

### 方式 B：Hugging Face Spaces（Docker 档已变为付费）
HF 的 **Docker Spaces 现在要求付费**（PRO/绑定账单），所以我们不再用它做免费部署。
若你已订阅 PRO，可参照旧文档用 `Dockerfile` 部署。

### 方式 C：Render（需信用卡验证，免费档本身不扣费）
Render 免费档要求绑定一张卡做身份验证（预授权 $1，不扣款）。有国际信用卡时：
- 打开 https://render.com/deploy?repo=https://github.com/77777square-spec/investment-workbench-backend
- 登录 → 授权 → Deploy；或手动 New Web Service → `python server.py` → Plan Free
- 得到 `https://xxx.onrender.com` 后，用 `server.py` 配套的前端 `investment-workbench.html` 填地址+Token

### 方式 D：学生本机运行 + 内网穿透（最快，零注册）
1. 学生电脑运行 `python server.py`（需装 Python）
2. 用 `ssh -R 80:localhost:8000 localhost.run` 或 cloudflared 生成公网网址
3. 把网址填到前端"服务地址"。依赖学生电脑在线，仅适合临时演示。

### 方式 E：纯静态演示（已部署，零后端）
前端已部署到 CloudStudio，老师打开即是一个完整工作台（待办可打勾 + 四块面板），
未配后端时显示"演示数据"。
