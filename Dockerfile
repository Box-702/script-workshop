# =====================================================================
# Dockerfile —— 剧本智能体 API 镜像
#
# 说明：本项目的前端是 FastAPI 内置的极简单页（app/web/index.html），
# 因此只需一个 API 镜像即可同时提供 REST API 与 Web 页面。
# 依赖使用 langgraph / langchain-openai / psycopg / pymilvus 等。
# =====================================================================

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先复制依赖声明与包，利用 Docker 层缓存加速后续重建。
COPY pyproject.toml README.md ./
COPY app ./app

# 安装（editable）：会把 app 作为 script-agent 包装进环境，并注册 cli 入口。
RUN python -m pip install --upgrade pip && \
    python -m pip install -e .

EXPOSE 8000

# 默认入口：uvicorn 提供 API + Web 页面。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
