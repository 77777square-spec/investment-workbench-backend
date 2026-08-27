# 投资顾问工作台后端 · Hugging Face Spaces（Docker 部署，无需信用卡）
# 直接运行 server.py；HF 会注入 $PORT（默认 7860），server.py 已读取该变量。
FROM python:3.11-slim

WORKDIR /app

# 复制全部文件：server.py + investment-workbench.html + 部署配置
COPY . /app

# 服务端会监听 0.0.0.0:$PORT
EXPOSE 7860

CMD ["python", "server.py"]
