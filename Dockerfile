# 抖音直播监控平台 Dockerfile
# 多阶段构建优化镜像大小

# ==================== 构建阶段 ====================
FROM python:3.11-slim as builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ==================== 运行阶段 ====================
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    # 应用配置
    DEBUG=False \
    LOG_LEVEL=INFO

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Node.js 用于 PyExecJS
    nodejs \
    # 时区设置
    tzdata \
    # 健康检查
    curl \
    && rm -rf /var/lib/apt/lists/* \
    # 设置时区
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 创建非 root 用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 设置工作目录
WORKDIR /app

# 复制应用代码
COPY --chown=appuser:appgroup . .

# 创建必要的目录
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appgroup /app/data /app/logs

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 7654

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7654/ || exit 1

# 启动命令
CMD ["python", "app.py"]
