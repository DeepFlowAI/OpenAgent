# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

# Build tools needed by bcrypt / oss2 crcmod C extensions.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# Default to PyPI official index. CN users can switch to a faster mirror:
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ .
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 3 \
    -i "${PIP_INDEX_URL}" \
    -r requirements.txt

COPY . .
RUN find . -name '._*' -delete

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
