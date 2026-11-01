FROM python:3.11-slim AS builder

# gcc + libc headers are needed to build tgcrypto when no prebuilt wheel matches the platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
RUN useradd --create-home --uid 10001 bot
COPY bot ./bot
COPY assets ./assets
USER bot

CMD ["python", "-m", "bot"]
