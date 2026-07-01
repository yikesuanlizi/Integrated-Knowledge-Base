FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 应用代码
COPY pyproject.toml ./
COPY app/ ./app/
COPY scripts/ ./scripts/

# Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# 工作目录（用于 wiki 输出、活动日志、导出等）
RUN mkdir -p /app/wiki_output /app/wiki_output/exports /app/wiki_output/activity_log

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
