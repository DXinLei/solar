# ============================================================
# 倪派紫微斗数真太阳时 API — Docker 镜像
# ============================================================
FROM python:3.11-slim

# ── 环境变量 ──────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# ── 系统依赖 ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 工作目录 ──────────────────────────────────────────
WORKDIR /solar

# ── 复制依赖声明（利用 Docker 分层缓存） ────────────
COPY pyproject.toml ./

# ── 安装 Python 依赖 ─────────────────────────────────
RUN pip install --no-cache-dir \
    apscheduler \
    ephem \
    fastapi \
    "lark-oapi" \
    pandas \
    pydantic \
    uvicorn

# ── 复制项目代码和数据 ──────────────────────────────
COPY app/ app/
COPY data/ data/

# 注意：ok_geo.csv（160MB）未纳入 Git，需手动放置到 data/ 目录
# 或从 release 中下载

# ── 暴露端口 ──────────────────────────────────────────
EXPOSE 8000

# ── 启动 ──────────────────────────────────────────────
# config.json 通过 volume 挂载到 /solar/config.json
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
