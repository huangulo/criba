# Criba
**Narrative Intelligence & Astroturfing Detection Engine**

Separating signal from noise — an open-source OSINT tool for detecting manufactured narratives, coordinated inauthentic behavior, and information operations.

---

![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)
![License: AGPLv3](https://img.shields.io/badge/License-AGPLv3-green.svg)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-blue.svg)
![Ollama](https://img.shields.io/badge/Ollama-Supported-orange.svg)

---

## Structural OSINT Philosophy

Criba does not analyze content sentiment. It analyzes BEHAVIOR patterns.

A high astroturfing score means the distribution mechanism is artificial — not that the content is false.

**Key detection signatures:**
- Lexical Similarity — copypasta detection via MinHash
- Temporal Clustering — unnatural posting schedules
- Account Age Anomalies — suspiciously new accounts
- Network Topology — tight clusters vs decentralized webs

> Criba does not tell you what to think. It shows you the structural patterns behind what you're seeing.

---

## Architecture

```
Ingest (Plugins) → Filter (Heuristics) → Analyze (Ollama LLM) → Cluster (pgvector) → Serve (FastAPI + Next.js)
                                                                               ↓
                                                                         PostgreSQL + pgvector
                                                                               ↓
                                                                              Redis
```

---

## How It Works

### Layer 1: Ingestion
Plugin system that collects data from multiple sources:
- Telegram
- Reddit
- RSS feeds
- Bluesky
- YouTube

### Layer 2: Heuristic Filters
Multi-stage filtering pipeline that typically only allows 5-15% of posts to reach LLM analysis:
- Language detection and filtering
- Deduplication
- Copypasta detection (MinHash)
- Temporal anomaly detection
- Account age analysis
- Hashtag co-occurrence analysis
- Network graph construction

### Layer 3: LLM Analysis
Local inference via Ollama with support for:
- Mistral 7B
- Llama 3.1 8B
- Qwen2.5 14B
- Mixtral 8x7B

### Layer 4: Clustering & Campaign Detection
- Semantic similarity clustering using pgvector
- Narrative tracking across time
- Campaign auto-detection and flagging

---

## Quick Start

```bash
git clone https://github.com/user/criba.git
cd criba
cp .env.example .env
# Edit .env with your credentials

# Install and run Ollama
curl -fsSL https://ollama.com/install.sh | sh && ollama pull qwen3.5:9b

# Start the application
docker compose up -d

# Access points
# Dashboard: http://localhost:3030
# API docs: http://localhost:8030/docs
```

---

## Configuration

The `criba.yml` file controls all major settings:

```yaml
general:
  language: es                 # primary analysis language (ISO 639-1)
  timezone: America/Bogota     # timezone for temporal analysis
  heuristic_threshold: 0.6     # composite score above this triggers LLM analysis

ollama:
  host: http://localhost:11434
  model: qwen3.5:9b           # or mistral:7b for lower VRAM
  timeout: 60

sources:
  telegram:
    enabled: true
    channels:
      - "@channel_name"
    poll_interval: 60          # seconds between polls

  reddit:
    enabled: true
    subreddits:
      - "Colombia"
    poll_interval: 120

  rss:
    enabled: true
    feeds:
      - name: "Feed Name"
        url: "https://example.com/rss.xml"
    poll_interval: 300

  bluesky:
    enabled: false
    keywords: []

  youtube:
    enabled: false
    channels: []

alerts:
  copypasta_threshold: 10      # flag if 10+ similar posts in 72h
  temporal_cluster_min: 5      # flag if 5+ posts in anomalous window
  new_account_days: 7          # flag accounts younger than this

notifications:
  slack_webhook_url: ""
  discord_webhook_url: ""
  telegram_bot_token: ""
  telegram_chat_id: ""
  confidence_threshold: 0.85   # minimum confidence to trigger alerts
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12 + FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| LLM Engine | Ollama (local inference) |
| Dashboard | Next.js 14 + Tailwind CSS |
| Graphing | D3.js |

---

## Use Cases

- Electoral monitoring — tracking disinformation campaigns
- Corporate reputation — identifying coordinated attacks
- Stock manipulation — detecting pump-and-dump patterns
- Journalism — source verification and narrative analysis
- NGO/Civil society — human rights documentation and monitoring

---

## Hardware Requirements

**Minimum:**
- 4 vCPU
- 16 GB RAM
- 100 GB SSD

**Recommended:**
- 8 vCPU
- 32 GB RAM
- 500 GB NVMe
- GPU with 12+ GB VRAM

---

## API Endpoints

- `GET /api/narratives` — List detected narratives
- `GET /api/campaigns` — List identified campaigns
- `GET /api/posts/flagged` — Retrieve flagged posts
- `GET /api/network/{id}` — Get network analysis for specific entity
- `GET /api/stats/summary` — Overall statistics and metrics
- `WS /ws/live` — WebSocket for real-time updates

---

## License

AGPLv3 — Free to use, modify, and deploy. Derivative works must remain open source.

---

*Criba: porque la verdad no necesita bots.*