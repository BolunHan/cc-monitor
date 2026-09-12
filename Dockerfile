FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/bolunhan/cc-monitor"
LABEL org.opencontainers.image.description="Monitor Claude Code working status via hooks"

# Version shown in registry metadata (GHCR and the GitLab registry read this
# label). Passed in by whatever runs the build rather than written here, so it
# cannot drift from the one source of truth in src/cc_monitor/__init__.py —
# `make docker-build` reads that file and the GitLab tag pipeline uses the tag.
# A bare `docker build .` therefore produces an image with no version label.
ARG CC_MONITOR_VERSION=""
LABEL org.opencontainers.image.version="${CC_MONITOR_VERSION}"

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

WORKDIR /app

# Let the server find static/ and hooks/ at /app
ENV CC_MONITOR_ROOT=/app
# Marker — server checks this to know it's running in Docker
RUN touch /app/.docker-env

COPY pyproject.toml .
COPY src/ src/
COPY static/ static/
COPY hooks/ hooks/

# Proxy-aware pip install
RUN if [ -n "${HTTP_PROXY}" ]; then \
      pip install --no-cache-dir --proxy "${HTTP_PROXY}" . ; \
    else \
      pip install --no-cache-dir . ; \
    fi

EXPOSE 9876

ENTRYPOINT ["cc-monitor", "--host", "0.0.0.0", "--port", "9876"]
