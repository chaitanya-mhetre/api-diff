# docker build -t api-diff . && docker run --rm -v "$PWD:/work" api-diff old.yaml new.yaml
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
WORKDIR /work
ENTRYPOINT ["/app/.venv/bin/api-diff"]
