# Build from the repository root: docker build -f web/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python:3.11-slim-trixie@sha256:cce12316475d7d56d605f76e1d811d0dc4e7227f2d4afd29951521264f504ff8 AS base
# Both pinned images include the eMudhra CA fix. uv replaces the base image's
# bundled pip from the lockfile without using it to bootstrap downloads.
ENV UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
# uv sync retains Python's seed packages even when they are not in the lock.
# Remove unused build seeds before syncing either stage.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv pip uninstall --system --offline setuptools wheel
WORKDIR /build
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
COPY web/pyproject.toml web/README.md ./web/
COPY web/scripts/check_tls.py /usr/local/libexec/treestamp-check-tls.py

FROM base AS build
# Third-party dependencies must have wheels; their builds cannot introduce
# dependencies outside the lock. Workspace packages are built below.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --package treestamp-web --no-default-groups \
        --group build --group runtime-tools --no-install-workspace --no-build \
    && python /usr/local/libexec/treestamp-check-tls.py
COPY src ./src
COPY web/src ./web/src
RUN python -m build --wheel --no-isolation --outdir /wheels . \
    && python -m build --wheel --no-isolation --outdir /wheels ./web

FROM base AS runtime
ARG BUILD_COMMIT=unknown
ENV BUILD_COMMIT=${BUILD_COMMIT} PORT=8000 PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.revision=${BUILD_COMMIT}
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --package treestamp-web --no-default-groups \
        --group runtime-tools --no-install-workspace --no-build \
    && python /usr/local/libexec/treestamp-check-tls.py
COPY --from=build /wheels /wheels
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv pip install --system --no-deps --no-index /wheels/*.whl \
    && python -m pip check \
    && python /usr/local/libexec/treestamp-check-tls.py \
    && rm -rf /wheels /build
WORKDIR /app
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz',timeout=3)"
CMD ["sh", "-c", "uvicorn --factory treestamp_web.app:create_app --host 0.0.0.0 --port ${PORT}"]
