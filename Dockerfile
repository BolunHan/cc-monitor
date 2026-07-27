FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/bolunhan/cc-monitor"
LABEL org.opencontainers.image.description="Monitor Claude Code working status via hooks"

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 9876

ENTRYPOINT ["cc-monitor", "--host", "0.0.0.0", "--port", "9876"]
