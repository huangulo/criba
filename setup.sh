#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { printf "${CYAN[INFO]}  %s${NC}\n" "$1"; }
ok()      { printf "${GREEN}[OK]    %s${NC}\n" "$1"; }
warn()    { printf "${YELLOW}[WARN]  %s${NC}\n" "$1"; }
fail()    { printf "${RED}[FAIL]  %s${NC}\n" "$1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -------------------------------------------------------
# 1. Docker & Docker Compose
# -------------------------------------------------------
info "Checking Docker..."
if command -v docker >/dev/null 2>&1; then
    DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    ok "Docker found (${DOCKER_VERSION:-unknown version})"
else
    fail "Docker is not installed."
    echo "       Install: https://docs.docker.com/get-docker/"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
    ok "Docker Compose found (v${COMPOSE_VERSION})"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker-compose version --short 2>/dev/null || echo "unknown")
    warn "Found legacy docker-compose (v${COMPOSE_VERSION}). Consider upgrading to Docker Compose v2."
else
    fail "Docker Compose is not installed."
    echo "       Install: https://docs.docker.com/compose/install/"
    exit 1
fi

# -------------------------------------------------------
# 2. .env file
# -------------------------------------------------------
info "Checking .env configuration..."
if [ -f .env ]; then
    ok ".env file exists"
else
    if [ ! -f .env.example ]; then
        fail ".env.example not found. Cannot create .env automatically."
        exit 1
    fi

    cp .env.example .env
    ok "Created .env from .env.example"

    echo ""
    info "Core credentials needed. Press Enter to skip any field."
    echo ""

    prompt_value() {
        local key="$1"
        local label="$2"
        local current
        current=$(grep "^${key}=" .env 2>/dev/null | cut -d'=' -f2-)
        if [ -z "$current" ]; then
            printf "  %s: " "$label"
            read -r value
            if [ -n "$value" ]; then
                if grep -q "^${key}=" .env 2>/dev/null; then
                    sed -i "s|^${key}=.*|${key}=${value}|" .env
                else
                    echo "${key}=${value}" >> .env
                fi
            fi
        fi
    }

    prompt_value "TELEGRAM_API_ID"   "Telegram API ID"
    prompt_value "TELEGRAM_API_HASH" "Telegram API Hash"
    prompt_value "TELEGRAM_PHONE"    "Telegram Phone Number"
    prompt_value "YOUTUBE_API_KEY"   "YouTube API Key"

    ok "Credentials saved to .env"
fi

# -------------------------------------------------------
# 3. Ollama
# -------------------------------------------------------
info "Checking Ollama..."

OLLAMA_HOST=$(grep "^OLLAMA_HOST=" .env 2>/dev/null | cut -d'=' -f2-)
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" .env 2>/dev/null | cut -d'=' -f2-)
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"

# Resolve host.docker.internal to localhost for local checks
OLLAMA_CHECK_URL=$(echo "$OLLAMA_HOST" | sed 's/host.docker.internal/localhost/')

check_ollama_model() {
    local model="$1"
    local models
    models=$(curl -sf "${OLLAMA_CHECK_URL}/api/tags" 2>/dev/null | grep -o "\"name\":\"[^\"]*${model}[^\"]*\"" || true)
    if [ -n "$models" ]; then
        ok "Ollama model '${model}' is available"
        return 0
    else
        warn "Ollama model '${model}' is NOT pulled."
        echo "       Run: ollama pull ${model}"
        return 1
    fi
}

if curl -sf "${OLLAMA_CHECK_URL}/api/tags" >/dev/null 2>&1; then
    ok "Ollama is reachable at ${OLLAMA_CHECK_URL}"

    check_ollama_model "${OLLAMA_MODEL}" || true
    check_ollama_model "nomic-embed-text" || true
else
    warn "Ollama is NOT reachable at ${OLLAMA_CHECK_URL}"
    echo "       The pipeline will still start but LLM analysis will be unavailable."
    echo "       Install: https://ollama.com"
    echo "       Then pull models:"
    echo "         ollama pull ${OLLAMA_MODEL}"
    echo "         ollama pull nomic-embed-text"
fi

# -------------------------------------------------------
# 4. Start
# -------------------------------------------------------
echo ""
info "Setup complete. Start the pipeline with:"
echo ""
echo "       docker compose up -d"
echo ""
echo "       Dashboard : http://localhost:3030"
echo "       API docs  : http://localhost:8030/docs"
echo ""
