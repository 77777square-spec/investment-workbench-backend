# 后端部署指南（老师电脑无需装 Python）

老师只需要在浏览器里打开**工作台网址**即可使用。真正的行情数据由一个"后端"在云端计算，
老师这边完全不需要安装 Python。老师填的 Tushare Token 只存在他自己的浏览器里，不会上传到任何服务器。

真实数据链路：
- 美股三大指数 / 日经 / 韩国综指 → Tushare `index_global`（老师填自己的 token）
- A股三大指数 → Tushare `index_daily`
- A股板块资金流 → 东方财富（无需 token）
- 美股板块/个股 → Yahoo Finance（服务端拉取，不受浏览器跨域限制）
- 热话题 / 政策资讯：暂为演示位，需接大模型或新闻源

---

## 方式 A（无信用卡，推荐）：Hugging Face Spaces

免费、**无需绑定信用卡**，后端可正常访问外网拉取行情，一个网址同时托管页面与接口。

1. 打开 https://huggingface.co/spaces  → 点右上角 **New Space**
2. Owner 选自己，Space name 填 `investment-workbench`（随意）→ **SDK 选择 Docker** → 点 Create Space
3. 进入该 Space 后，左侧选 **Settings → Repository** → 连接你的 GitHub 仓库
   `77777square-spec/investment-workbench-backend`（或先 Fork 到你自己账号）
4. 也可以不改 GitHub，直接在 Space 的 **Files** 里把仓库文件（server.py / investment-workbench.html / Dockerfile 等）上传上去
5. HF 会自动按 `Dockerfile` 构建并启动，几分钟后顶部出现蓝绿网址 `https://你的账号-investment-workbench.hf.space`
6. 老师打开该网址 → 点右上角「⚙️ 接入实时数据」→ **只粘贴自己的 32 位 Tushare Token**（服务地址留空）→ 保存 → 刷新看板，即见实时行情

> 注意：免费 Space 长时间无人访问会"休眠"，首次打开需要等约 10 秒唤醒，属正常。

---

## 方式 B：Render（需要信用卡验证，免费档本身不扣费）

Render 免费档也要求绑定一张卡做身份验证（预授权 $1，不扣款）。若你/老师有国际信用卡，最省事：

1. 仓库已推到 GitHub：https://github.com/77777square-spec/investment-workbench-backend
2. 打开 https://render.com/deploy?repo=https://github.com/77777square-spec/investment-workbench-backend
3. 用 GitHub 登录 → 授权 → 直接点 Deploy（render.yaml 已配好）
4. 若手动：New Web Service → 选仓库 → Runtime Python 3 → Build Command 留空 → Start Command `python server.py` → Plan Free
5. 部署完得到 `https://xxx.onrender.com`，老师照方式 A 第 6 步填 Token 即可

---

## 方式 C：学生本机运行 + 内网穿透（最快，无需注册任何云）

1. 学生电脑（已装好 Python）运行：`python server.py`
2. 再用一条免费穿透命令把本机端口暴露为公网网址（任选其一）：
   - `ssh -R 80:localhost:8000 localhost.run`
   - 或使用 cloudflared / bore 等工具
3. 把得到的公网网址填到前端"服务地址"即可。
   注意：此方式依赖学生电脑在线；长期给老师用建议用方式 A/B。

---

## 方式 D：纯静态演示（已部署，零后端）

前端已部署到 CloudStudio，老师打开即是一个完整的工作台（每日待办可打勾 + 四块面板）。
未配置后端时显示"演示数据"，配置后端网址 + token 后即变为实时行情。
