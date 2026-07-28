FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/bolunhan/cc-monitor"
LABEL org.opencontainers.image.description="Monitor Claude Code working status via hooks"

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY static/ static/
COPY hooks/ hooks/
COPY .claude/ .claude/

# Proxy-aware pip install
RUN if [ -n "${HTTP_PROXY}" ]; then \
      pip install --no-cache-dir --proxy "${HTTP_PROXY}" . ; \
    else \
      pip install --no-cache-dir . ; \
    fi

EXPOSE 9876

ENTRYPOINT ["cc-monitor", "--host", "0.0.0.0", "--port", "9876"]
