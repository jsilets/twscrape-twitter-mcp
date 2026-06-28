FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TWSCRAPE_TWITTER_MCP_HOME=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

# twscrape's sqlite account pool lives here; mount a volume to persist sessions.
VOLUME ["/data"]
EXPOSE 8080

# Serve over HTTP for Fly/Railway. Set TWSCRAPE_TWITTER_MCP_AUTH_TOKEN to require a bearer token.
CMD ["twscrape-twitter-mcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
