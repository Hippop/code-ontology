# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS web-builder
WORKDIR /workspace/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY web/ ./
RUN npm run build

FROM node:24-bookworm-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CODE_ONTOLOGY_DB=/var/lib/code-ontology/platform.db \
    CODE_ONTOLOGY_RULES=/opt/code-ontology/rules/requirement-change-planning-rules.yaml \
    CODE_ONTOLOGY_WEB_ROOT=/opt/code-ontology/web/dist
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git openjdk-17-jre-headless python3 python3-pip \
    && npm install --global opencode-ai@1.18.5 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/code-ontology
COPY pyproject.toml README.md ./
COPY src/ src/
COPY rules/ rules/
COPY ontology/ ontology/
COPY shapes/ shapes/
COPY .opencode/ .opencode/
COPY opencode.json ./
COPY --from=web-builder /workspace/web/dist web/dist/
RUN python3 -m pip install --break-system-packages --no-cache-dir .
RUN useradd --create-home --uid 10001 platform \
    && mkdir -p /var/lib/code-ontology \
    && chown -R platform:platform /var/lib/code-ontology /opt/code-ontology
USER platform
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=3s --retries=5 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["code-ontology-platform", "serve", "--host", "0.0.0.0", "--port", "8080"]
