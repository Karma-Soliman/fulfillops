FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN python -m venv /opt/venv \
    && python -m pip install --no-cache-dir uv==0.7.3 \
    && VIRTUAL_ENV=/opt/venv /usr/local/bin/uv sync --frozen --no-dev --no-install-project --active

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS runtime
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=dev \
    LOG_LEVEL=INFO
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
COPY app /app/app
COPY entrypoint.sh /usr/local/bin/fulfillops
RUN chmod 0555 /usr/local/bin/fulfillops
USER 10001:10001
EXPOSE 8080 9100
ENTRYPOINT ["/usr/local/bin/fulfillops"]
CMD ["api"]
