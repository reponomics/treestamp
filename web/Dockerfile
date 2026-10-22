# Build from the repository root: docker build -f web/Dockerfile .
FROM python:3.11-slim-trixie@sha256:cce12316475d7d56d605f76e1d811d0dc4e7227f2d4afd29951521264f504ff8 AS base
# This digest includes Debian's eMudhra CA fix. Bootstrap the old bundled pip
# using that repaired system bundle, then retain patched pip in both stages.
RUN python -m pip --isolated --cert /etc/ssl/certs/ca-certificates.crt install \
    --no-cache-dir --upgrade 'pip>=26.2.2' 'certifi>=2026.10.19'
COPY web/scripts/check_tls.py /usr/local/libexec/treestamp-check-tls.py
RUN python /usr/local/libexec/treestamp-check-tls.py

FROM base AS build
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY web/pyproject.toml web/README.md ./web/
COPY web/src ./web/src
RUN python -m pip install --no-cache-dir --prefix=/install . ./web

FROM base AS runtime
ARG BUILD_COMMIT=unknown
ENV BUILD_COMMIT=${BUILD_COMMIT} PORT=8000 PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.revision=${BUILD_COMMIT}
COPY --from=build /install /usr/local
RUN python /usr/local/libexec/treestamp-check-tls.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz',timeout=3)"
CMD ["sh", "-c", "uvicorn --factory treestamp_web.app:create_app --host 0.0.0.0 --port ${PORT}"]
