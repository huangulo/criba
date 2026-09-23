# Criba

**Narrative Intelligence & Astroturfing Detection Engine**

*Separating signal from noise — an open-source OSINT tool for detecting manufactured narratives, coordinated inauthentic behavior, and information operations.*

---

## What Criba Does

Criba is a self-hosted pipeline that monitors public data sources, identifies narrative patterns, and detects astroturfing campaigns. It answers one question: **"Is this organic or manufactured?"**

It is not a sentiment analysis tool. It is not a poll predictor. It is a structural pattern detector that exposes the mechanical fingerprints left behind by coordinated information operations.

---

## Use Cases

- **Electoral monitoring** — Detect manufactured support/panic campaigns during elections
- **Corporate reputation** — Identify coordinated attacks or fake grassroots campaigns against brands
- **Stock manipulation** — Flag pump-and-dump narrative campaigns on financial forums
- **Journalism** — Provide reporters with evidence of coordinated inauthentic behavior
- **NGO/Civil society** — Monitor disinformation campaigns targeting vulnerable populations

---

## Core Concepts

### Narrative Momentum

Measures the velocity, acceleration, and cross-platform spread of a specific talking point. A narrative has real momentum when it breaches isolated communities and forces broader public reaction.

**Tracking Metrics:**

- **Platform Bleed** — A narrative originates in a closed ecosystem (e.g., a partisan Telegram channel) and jumps to public forums (Reddit, Bluesky), eventually forcing coverage by news outlets. Criba tracks this chain.
- **Engagement-to-Originator Ratio** — Organic momentum generates massive secondary engagement (shares, quotes, organic replies) from a few original posts. Manufactured momentum requires constant, high-volume posting by a core group of accounts.
- **Keyword Mutation** — Organic narratives evolve. Real people alter phrasing, add slang, create memes. If a narrative scales but the exact phrasing remains static, it lacks organic momentum.

### Astroturfing Detection

Astroturfing is the artificial simulation of grassroots support or outrage. Because it is a mechanical process, it leaves structural fingerprints.

**Detection Signatures:**

- **Lexical Similarity (Copypasta)** — High volumes of posts using exact phrasing, identical hashtags in the same order, or slight, predictable variations indicating cheap LLM generation.
- **Temporal Clustering** — Unnatural posting schedules. Organic trends follow human waking hours and news cycles. Astroturfing features coordinated spikes where hundreds of accounts post within a tight, artificial window (e.g., a massive spike at 3:14 AM).
- **Account Age & History Anomalies** — A sudden surge in political messaging from accounts created in the same week, or from dormant accounts that previously only posted about unrelated topics.
- **Network Topology** — Organic trends produce decentralized webs. Astroturfed campaigns produce tight, isolated clusters where accounts only follow, retweet, and reply to each other.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CRIBA PIPELINE                           │
│                                                                 │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐ │
│  │ INGEST    │───▶│ FILTER    │───▶│ ANALYZE   │───▶│ SERVE  │ │
│  │ (Plugins) │    │ (Heurist.)│    │ (Ollama)  │    │ (API)  │ │
│  └───────────┘    └───────────┘    └───────────┘    └────────┘ │
│       │                │                │                │      │
│       ▼                ▼                ▼                ▼      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL + pgvector                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ▲                                                         │
│       │                                                         │
│  ┌─────────┐                                                    │
│  │  Redis  │  (task queue / message broker)                     │
│  └─────────┘                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1: Ingestion (Plugin System)

Each data source is a self-contained plugin that implements a standard interface. This allows contributors to add new sources without touching core logic.

**Plugin Interface:**

```python
class SourcePlugin(ABC):
    """Base class for all data source plugins."""

    @abstractmethod
    def get_name(self) -> str:
        """Unique identifier for this source (e.g., 'telegram', 'reddit')."""

    @abstractmethod
    def get_config_schema(self) -> dict:
        """JSON schema for required configuration (API keys, channels, etc.)."""

    @abstractmethod
    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        """Yield raw posts from the source. Runs as a Celery task."""

    @abstractmethod
    def get_rate_limits(self) -> RateLimitConfig:
        """Return rate limit parameters for this source."""
```

**RawPost Schema (normalized across all sources):**

```python
@dataclass
class RawPost:
    source: str              # plugin name
    source_id: str           # unique ID on the platform
    author_id: str           # platform-specific author identifier
    author_handle: str       # display name or username
    author_created_at: datetime | None  # account creation date (if available)
    content: str             # raw text content
    language: str | None     # ISO 639-1 code (detected or provided)
    published_at: datetime   # when the post was published
    url: str | None          # permalink (if public)
    engagement: dict         # {"likes": 0, "shares": 0, "replies": 0, ...}
    hashtags: list[str]      # extracted hashtags
    mentions: list[str]      # mentioned accounts
    reply_to: str | None     # source_id of parent post (if reply)
    media_urls: list[str]    # attached images/videos
    raw_metadata: dict       # source-specific fields preserved as-is
```

**Phase 1 Plugins (Colombia focus):**

| Plugin | Library | Free Tier | Notes |
|--------|---------|-----------|-------|
| Telegram | Telethon | Yes (user session) | Richest political data in LATAM. Requires phone number for session auth. Monitor public channels/groups. |
| Reddit | PRAW (OAuth) | ~100 req/min | r/Colombia, r/politics equivalents. Free with OAuth app credentials. |
| RSS/News | feedparser | Unlimited | El Tiempo, El Espectador, Semana, Blu Radio, Caracol. Zero cost. |
| Bluesky | AT Protocol | Unlimited | Growing adoption. Fully open API. |
| YouTube | yt-dlp | Unlimited | Comment extraction from political channels. Underrated signal source. |

**Future Plugins (expansion):**

| Plugin | Notes |
|--------|-------|
| Mastodon/Fediverse | Open API, useful for US/EU |
| 4chan/8kun | Anonymous boards, high noise, valuable for tracking narrative origins |
| Facebook Pages | Meta Content Library (academic access required) |
| TikTok | Research API (academic access required) |
| X/Twitter | Paid API only — community can fund if needed |

### Layer 2: Heuristic Filters (No LLM Required)

Before any post touches the LLM, cheap computational filters classify it. This is critical for running on consumer hardware. **The goal: only 5-15% of ingested posts should reach the LLM layer.**

**Filter Pipeline:**

```
Raw Post ──▶ Language Detection
           ──▶ Deduplication (MinHash / SimHash)
           ──▶ Copypasta Detection (fuzzy string matching, n-gram fingerprinting)
           ──▶ Temporal Anomaly Scoring (posting time vs. local timezone norms)
           ──▶ Account Age Flagging (new account + political content = elevated score)
           ──▶ Hashtag Co-occurrence Clustering
           ──▶ Network Graph Update (author interaction edges)
           ──▶ Anomaly Score Assignment (0.0 - 1.0)
```

Posts scoring above a configurable threshold (default: 0.6) are queued for LLM analysis. Posts below are stored with their heuristic scores but never sent to the LLM.

**Key Heuristic Implementations:**

- **Copypasta Detector:** MinHash locality-sensitive hashing. Computes shingle sets (5-word windows) per post and compares against a rolling 72-hour corpus. Jaccard similarity > 0.7 across 3+ unique authors = flagged.
- **Temporal Anomaly:** Build a per-source hourly posting distribution from the first 7 days of ingestion (baseline). Flag posts that arrive during statistically dead hours (< 2nd percentile of the baseline distribution) in clusters of 5+.
- **Network Mapper:** Incremental graph construction using adjacency lists in PostgreSQL. On each post, update edges for: reply-to, mention, quote. Run community detection (Louvain algorithm) hourly to identify tight clusters.

### Layer 3: LLM Analysis (Ollama)

Only posts flagged by heuristic filters reach this layer. The local Ollama instance performs deeper contextual analysis.

**Recommended Models:**

| Model | VRAM | Use Case |
|-------|------|----------|
| Qwen3.5 9B | 8 GB | Default model, strong multilingual (current) |
| Mistral 7B | 6 GB | Fast classification, good multilingual |
| Llama 3.1 8B | 8 GB | Best reasoning at small size |
| Qwen2.5 14B | 12 GB | Superior Spanish/multilingual performance |
| Mixtral 8x7B | 24 GB | Best quality if hardware allows |

**Analysis Prompt Template:**

```
You are a narrative analysis engine. Evaluate the following social media post
and its metadata for signs of coordinated inauthentic behavior.

Context:
- Source: {source}
- Author account age: {account_age_days} days
- Author's previous topics: {topic_history}
- Heuristic anomaly score: {anomaly_score}
- Similar posts in last 72h: {copypasta_count}
- Temporal anomaly: {temporal_flag}

Post content:
"{content}"

Evaluate and respond in JSON:
{
  "coordination_probability": 0.0-1.0,
  "reasoning": "brief explanation",
  "narrative_category": "one of: political_support, political_attack, fear_campaign, fundraising_trigger, distraction, organic",
  "detected_language": "ISO 639-1",
  "talking_points_extracted": ["list", "of", "key", "claims"],
  "recommended_action": "one of: flag_for_review, add_to_cluster, dismiss, escalate"
}
```

### Layer 4: Storage (PostgreSQL + pgvector)

**Core Tables:**

```sql
-- Raw ingested posts
CREATE TABLE posts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(50) NOT NULL,
    source_id       VARCHAR(255) NOT NULL,
    author_id       VARCHAR(255) NOT NULL,
    author_handle   VARCHAR(255),
    author_created  TIMESTAMPTZ,
    content         TEXT NOT NULL,
    language        VARCHAR(10),
    published_at    TIMESTAMPTZ NOT NULL,
    url             TEXT,
    engagement      JSONB DEFAULT '{}',
    hashtags        TEXT[] DEFAULT '{}',
    mentions        TEXT[] DEFAULT '{}',
    reply_to        VARCHAR(255),
    raw_metadata    JSONB DEFAULT '{}',
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, source_id)
);

-- Heuristic scores (computed per post)
CREATE TABLE heuristic_scores (
    post_id             UUID PRIMARY KEY REFERENCES posts(id),
    copypasta_score     FLOAT DEFAULT 0.0,
    temporal_anomaly    FLOAT DEFAULT 0.0,
    account_age_flag    FLOAT DEFAULT 0.0,
    composite_score     FLOAT DEFAULT 0.0,
    sent_to_llm         BOOLEAN DEFAULT FALSE,
    scored_at           TIMESTAMPTZ DEFAULT NOW()
);

-- LLM analysis results
CREATE TABLE llm_analysis (
    post_id                 UUID PRIMARY KEY REFERENCES posts(id),
    coordination_probability FLOAT,
    reasoning               TEXT,
    narrative_category      VARCHAR(50),
    talking_points          TEXT[],
    recommended_action      VARCHAR(50),
    model_used              VARCHAR(100),
    analyzed_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Narrative clusters (groups of related talking points)
CREATE TABLE narratives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label           VARCHAR(255),
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    post_count      INTEGER DEFAULT 0,
    platform_spread INTEGER DEFAULT 0,  -- number of distinct platforms
    status          VARCHAR(50) DEFAULT 'active',  -- active, fading, dead
    embedding       vector(768)  -- pgvector for semantic similarity
);

-- Junction: posts <-> narratives
CREATE TABLE narrative_posts (
    narrative_id    UUID REFERENCES narratives(id),
    post_id         UUID REFERENCES posts(id),
    PRIMARY KEY (narrative_id, post_id)
);

-- Author interaction graph (adjacency list)
CREATE TABLE author_graph (
    source_author   VARCHAR(255),
    target_author   VARCHAR(255),
    interaction     VARCHAR(50),  -- reply, mention, quote, retweet
    weight          INTEGER DEFAULT 1,
    last_seen       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_author, target_author, interaction)
);

-- Detected astroturfing campaigns
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label           VARCHAR(255),
    description     TEXT,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    confidence      FLOAT,
    account_count   INTEGER,
    post_count      INTEGER,
    platforms       TEXT[],
    status          VARCHAR(50) DEFAULT 'active'
);

-- Project-scoped monitoring targets (dynamic, managed via dashboard)
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE project_targets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id) NOT NULL,
    platform    VARCHAR(50) NOT NULL,
    target_type VARCHAR(20) NOT NULL,  -- 'keyword' or 'handle'
    value       VARCHAR(500) NOT NULL
);

-- Runtime configuration (replaces YAML for dynamic settings)
CREATE TABLE system_settings (
    key   VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
```

### Layer 5: API (FastAPI)

```
GET  /api/narratives              — Active narratives, sorted by momentum
GET  /api/narratives/{id}         — Narrative detail with associated posts
GET  /api/narratives/{id}/timeline — Platform bleed timeline
GET  /api/campaigns               — Detected astroturfing campaigns
GET  /api/campaigns/{id}          — Campaign detail with accounts and posts
GET  /api/posts/flagged           — Flagged posts with heuristic + LLM scores
GET  /api/posts/log               — Raw ingestion log (unflagged posts, baseline noise, filterable by platform/score)
GET  /api/stats/dashboard         — Aggregate stats for the dashboard
GET  /api/graph/clusters          — Current network topology clusters
GET  /api/graph/account/{id}      — Interaction graph for a specific account
GET/PUT /api/settings/notifications — Notification channel configuration (DB-backed)
GET/PUT /api/settings/baseline    — Heuristic threshold configuration (DB-backed)
GET  /api/projects                — List active monitoring projects with targets
POST /api/projects                — Create project with assigned targets
DELETE /api/projects/{id}         — Delete project and cascade targets
WS   /ws/alerts                   — WebSocket feed for real-time alerts
```

### Layer 6: Dashboard (Next.js)

**Views:**

1. **Live Feed** — Real-time stream of flagged posts with anomaly scores
2. **Narrative Map** — Bubble chart showing active narratives sized by momentum, colored by platform spread
3. **Campaign Inspector** — Drill-down into detected astroturfing operations showing account clusters, posting timelines, and lexical similarity scores
4. **Raw Ingestion Log (Firehose)** — Slide-over panel showing unflagged posts with filters for platform and max composite score, enabling audit of baseline noise
5. **Network Graph** — Interactive force-directed graph of author interactions, highlighting tight clusters
6. **Projects & Settings Console** — Three-tab management panel: baseline threshold sliders (heuristic, copypasta, temporal cluster, new account days), project builder with target injector, and active projects matrix with delete
7. **Source Health** — Monitoring panel for plugin status, ingestion rates, and error logs

---

## Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| Ingestion Workers | Python 3.12 + Celery | Async task queue with horizontal scaling |
| Message Broker | Redis 7 | Lightweight, proven with Celery |
| Database | PostgreSQL 16 + pgvector | Relational + vector similarity search |
| LLM Engine | Ollama | Local inference, zero API costs, model flexibility |
| API | FastAPI | Async Python, auto-generated OpenAPI docs |
| Dashboard | Next.js 14 | React ecosystem, SSR for SEO if needed |
| Graphing | D3.js | Network topology visualization |
| Containerization | Docker Compose | Single-command deployment |
| Language Detection | lingua-py | Offline, supports 75 languages |

---

## Deployment

### Minimum Hardware (Colombia-scale, ~50K posts/day)

- 4 vCPUs
- 16 GB RAM (8 GB for Ollama + 8B model)
- 100 GB SSD
- No GPU required for 7-8B models (CPU inference is viable)

### Recommended Hardware (Multi-country, ~500K posts/day)

- 8 vCPUs
- 32 GB RAM
- 500 GB NVMe SSD
- GPU with 12+ GB VRAM (for 14B+ models)

### Quick Start

```bash
git clone https://github.com/[your-handle]/criba.git
cd criba
cp .env.example .env
# Edit .env with your Telegram session, Reddit OAuth, etc.
docker compose up -d
# Access dashboard at http://localhost:3030
# Access API docs at http://localhost:8030/docs
```

---

## Configuration

```yaml
# criba.yml — Infrastructure-only configuration
# Monitoring targets and alert settings are managed in the database
# via the dashboard (Projects & Settings console) or API endpoints.
general:
  language: es            # primary analysis language
  timezone: America/Bogota

ollama:
  host: http://host.docker.internal:11434  # Docker → host Ollama
  model: qwen3.5:9b       # or mistral:7b for lower VRAM
  timeout: 30

sources:
  telegram:
    enabled: true
    poll_interval: 60      # seconds

  reddit:
    enabled: true
    poll_interval: 120

  rss:
    enabled: true
    poll_interval: 300

  bluesky:
    enabled: true
    poll_interval: 120

  youtube:
    enabled: true
    poll_interval: 900
```

### Runtime Configuration (Database-Backed)

The following settings are stored in the `system_settings` table and can be modified at runtime through the API and dashboard without restarting services:

| Setting Key | Default | Description |
|-------------|---------|-------------|
| `heuristic_threshold` | 0.6 | Composite score above this triggers LLM analysis |
| `copypasta_threshold` | 10 | Flag if this many similar posts in 72h |
| `temporal_cluster_min` | 5 | Flag if this many posts in anomalous window |
| `new_account_days` | 7 | Flag accounts younger than this |
| `confidence_threshold` | 0.85 | Campaign confidence required to trigger alerts |
| `slack_webhook_url` | "" | Slack notification webhook |
| `discord_webhook_url` | "" | Discord notification webhook |
| `telegram_bot_token` | "" | Telegram bot token for notifications |
| `telegram_chat_id` | "" | Telegram chat ID for notifications |

Monitoring targets (channels, feeds, subreddits, keywords, handles) are managed through the `projects` and `project_targets` tables. When a Celery ingestion task runs, `_ingest_source_async` queries `project_targets` for the matching platform and builds the source config (channels, keywords, handles) from the database rows. If no targets exist for a platform, the task skips. New targets added via the dashboard are picked up automatically by the next Celery beat cycle — no restart required.

The `criba.yml` file is now **infrastructure-only**: Ollama host/model, source `enabled` flags, and poll intervals. All monitoring targets (channels, feeds, subreddits, keywords, handles) are managed exclusively through the `project_targets` table. Source-specific configuration (channels, feeds, subreddits) has been removed from YAML entirely.

### API Authentication

Set `CRIBA_API_KEY` in `.env` to require authentication on every API route: REST calls must send the `X-API-Key` header, and the dashboard WebSocket connects with `?api_key=`. The dashboard image is built with the same key (`NEXT_PUBLIC_API_KEY` build arg), so keep the variable named `CRIBA_API_KEY` for docker compose to inject it into both the API and the dashboard build. When unset, the API runs without authentication (local development only).

---

## Development Phases

### Phase 1: Foundation — Completed ✅
- [x] Project scaffold (Docker Compose: PostgreSQL 16 + pgvector, Redis 7, Celery worker/beat, FastAPI, Next.js dashboard)
- [x] Plugin interface definition (`SourcePlugin` ABC, `RawPost` dataclass, `RateLimitConfig`, plugin registry)
- [x] Telegram plugin (Telethon-based, Colombia political channels)
- [x] RSS plugin (feedparser-based, Colombian news outlets)
- [x] Database schema migrations (Alembic: initial schema + post_embeddings table)
- [x] Heuristic filter pipeline (7 filters: language, deduplication, copypasta, temporal anomaly, account age, hashtag co-occurrence, network graph)

### Phase 2: Analysis Engine — Completed ✅
- [x] Ollama integration with structured JSON analysis prompt (`OllamaClient`, `build_analysis_prompt`)
- [x] Ollama embedding client (`OllamaEmbeddingClient` with `nomic-embed-text`, pgvector storage)
- [x] Narrative clustering via cosine similarity on pgvector embeddings (`NarrativeEngine.cluster_posts`)
- [x] Network graph construction and cluster detection (BFS-based community detection in API layer)
- [x] Platform bleed tracking (per-narrative, computed in campaign inspector)
- [x] Campaign auto-detection with multi-factor confidence scoring (`NarrativeEngine.detect_campaigns`)

### Phase 3: API & Dashboard — Completed ✅
- [x] FastAPI endpoints:
  - `GET /api/narratives` — Active narratives sorted by momentum
  - `GET /api/campaigns` — Detected campaigns sorted by confidence
  - `GET /api/posts/flagged` — Flagged posts with heuristic + LLM scores
  - `GET /api/stats/summary` — Aggregate dashboard statistics
  - `GET /api/network/{narrative_id}` — Interaction graph with cluster detection
  - `GET /api/campaigns/{id}/inspect` — Campaign forensic detail (copypasta phrases, platform bleed, identity ratio, evidence summary)
  - `GET/PUT /api/settings/notifications` — Notification channel configuration
  - `POST /api/alerts/test/{channel}` — Test alert delivery
- [x] WebSocket live feed (`/ws/alerts` with `ConnectionManager` for real-time broadcast)
- [x] Next.js dashboard with components: LiveAlerts, NarrativeMap, CampaignList, CampaignInspector, NetworkGraph, StatsSummary, AlertSettings, IngestionLog (Firehose), ProjectConsole
- [x] Celery beat schedule for automated ingestion (Telegram 60s, RSS 300s, Reddit 120s, Bluesky 120s, YouTube 900s), LLM analysis (120s), embedding generation (180s), narrative clustering (300s), campaign detection (600s). Ingestion tasks query `project_targets` from the database for platform-specific channels/keywords.

### Phase 4: Expansion — In Progress

**Completed:**
- [x] Reddit plugin (PRAW-based, subreddit monitoring with configurable poll interval)
- [x] Bluesky plugin (AT Protocol, keyword + handle tracking, `atproto` library)
- [x] YouTube comments plugin (yt-dlp-based, channel comment extraction with Google API fallback)
- [x] Alert system — Slack, Discord, Telegram notifications on campaign detection with configurable confidence threshold
- [x] Notification settings API (`GET/PUT /api/settings/notifications`, `POST /api/alerts/test/{channel}`)
- [x] Colombia deployment configuration (seeded via Projects system: Telegram channels, RSS feeds, Reddit subreddits, Bluesky keywords/handles, YouTube political channels — no longer hardcoded in `criba.yml`)
- [x] **Raw Ingestion Log** — `GET /api/posts/log` endpoint + Firehose slide-over panel for auditing unflagged posts and baseline noise
- [x] **Dynamic configuration from database** — `system_settings` table replaces YAML for runtime-tunable parameters (heuristic thresholds, alert settings, notification channels). No restart needed to apply changes. All notification/baseline reads in `alerts.py`, `engine/tasks.py`, `scoring.py`, and `routes.py` now query `system_settings` instead of `load_config()`.
- [x] **Projects & Targets system** — `projects` + `project_targets` tables with full CRUD API. Celery ingestion tasks (`_ingest_source_async`) now query `project_targets` by platform from the database instead of parsing `criba.yml`. The `criba.yml` sources section only controls `enabled` flag and `poll_interval`; channels/keywords/feeds are fully database-driven.
- [x] **Baseline Settings Console** — `GET/PUT /api/settings/baseline` + dashboard UI with threshold sliders. Backend uses `get_heuristic_threshold()` async helper that reads from `system_settings`.
- [x] **Project Console** — Three-tab management panel (Baseline, Projects, Active) integrated into dashboard header. Supports project CRUD with multi-target injection per platform.
- [x] **Alembic migration** — `a1b2c3d4e5f6_projects_and_settings` creates `projects`, `project_targets`, and `system_settings` tables with seeded defaults.
- [x] **Docker restart policies** — All services now use `restart: unless-stopped` for production resilience.

**Remaining:**

#### Multi-Language Analysis
Currently the system is configured for Spanish (`general.language: es`) with a single timezone (`America/Bogota`). Multi-language support requires:
- [ ] **Language-aware LLM prompts** — The analysis prompt template (`src/criba/llm/prompt.py`) is English-only. Need localized prompt variants for Portuguese and English that instruct the model to reason and categorize in the target language.
- [ ] **Per-source language config** — Allow `criba.yml` to specify a `language` per source so that, e.g., a Portuguese Telegram group and a Spanish RSS feed can coexist in the same deployment.
- [ ] **Language-specific heuristic tuning** — Copypasta shingle size (currently 5 words), hashtag co-occurrence thresholds, and temporal anomaly baselines may need adjustment per language. The `LanguageFilter` currently detects language but does not gate downstream filter behavior by it.
- [ ] **Multi-timezone ingestion** — Temporal anomaly detection (`TemporalAnomalyFilter`) builds baselines against UTC/local time. When monitoring multiple countries, each source needs its own timezone context for accurate anomaly scoring (e.g., a 3 AM spike in Bogota ≠ suspicious in London).
- [ ] **Dashboard internationalization** — The Next.js dashboard has no i18n layer. Need `next-intl` or equivalent for Spanish, Portuguese, and English UI translations.

#### Regional Deployment Profiles
- [ ] **Brazil configuration** — Portuguese language, `America/Sao_Paulo` timezone, Brazilian Telegram groups, local RSS feeds (Folha, G1, Estadão), relevant subreddits.
- [ ] **US configuration** — English language, multi-timezone (EST/PST), political subreddits, Bluesky handles for US politicians, RSS from major outlets.
- [ ] **Mexico configuration** — Spanish language, `America/Mexico_City` timezone, Mexican political Telegram/RSS sources.
- [ ] **Config profile switching** — `criba.yml` currently ships as a single file. Need a `--profile` flag or `criba.profiles/` directory with pre-built configs that can be loaded per deployment.

#### Future Source Plugins
- [ ] **Mastodon/Fediverse** — Open API, high adoption in EU. Useful for tracking narratives in German, French, and Spanish-speaking Mastodon instances.
- [ ] **4chan/8kun** — Anonymous image boards. High noise but extremely valuable for tracking narrative origins before they surface on mainstream platforms. Requires aggressive filtering.
- [ ] **Facebook Pages** — Meta Content Library access (academic/research only). Limited to approved researchers.
- [ ] **TikTok** — Research API (academic access). Video content requires transcript extraction before text analysis.

### Phase 5: Community & Production Readiness — Not Started

Phase 5 is about making Criba deployable by anyone — journalists, NGOs, researchers, and civic organizations — without needing to read the source code.

#### Documentation
- [x] Contributor guide (`CONTRIBUTING.md`) — Covers plugin development, filter creation, project structure, and PR process.
- [ ] **Deployment guide** — Step-by-step for non-technical users: VPS provisioning, Docker setup, Ollama model selection, `criba.yml` tuning, first data ingestion.
- [ ] **Plugin authoring tutorial** — While `CONTRIBUTING.md` covers the interface, a standalone tutorial with a real-world example (e.g., building a Mastodon plugin from scratch) would lower the barrier for external contributors.
- [ ] **API reference** — Auto-generated from FastAPI's OpenAPI spec, but needs a human-readable guide with authentication, pagination, filtering examples, and WebSocket protocol documentation.
- [ ] **Architecture deep-dive** — How data flows from ingestion → filters → LLM → clustering → campaign detection. Useful for contributors modifying core logic.

#### Pre-Built Configurations
- [x] Colombia profile — Seed data for political channels, news RSS, relevant subreddits, Bluesky keywords (managed via Projects system, not `criba.yml`)
- [ ] **Brazil profile** — `criba.profiles/brazil.yml` with Portuguese sources.
- [ ] **US profile** — `criba.profiles/us.yml` with English sources.
- [ ] **Mexico profile** — `criba.profiles/mexico.yml` with Mexican sources.
- [ ] **Profile installer** — CLI command (`criba init --profile=brazil`) that copies the right config, sets language/timezone defaults, and suggests relevant Ollama models.

#### Academic Research Export
Criba's data is valuable for computational social science, disinformation research, and media studies. Researchers need structured exports they can analyze in R, Python, or SPSS.
- [ ] **CSV/TSV export** — Flat file export of posts, scores, and analysis results. Filterable by date range, source, campaign, narrative.
- [ ] **JSON-LD export** — Structured, linked-data format for integration with academic knowledge graphs. Includes provenance metadata (when detected, confidence, methodology).
- [ ] **GraphML / GEXF export** — Network graph exports (author interaction graph, narrative cluster graph) for analysis in Gephi, NetworkX, or igraph.
- [ ] **Bibliographic metadata** — Attach dataset DOI, collection methodology, and citation information to exports so researchers can reference Criba datasets in publications.
- [ ] **API endpoint** — `GET /api/export?format=csv&campaign={id}&from={date}&to={date}` for programmatic access.

#### Production Hardening
- [ ] **Authentication & authorization** — Currently the API has no auth. Need API key or OAuth2 layer for multi-user deployments.
- [ ] **Rate limiting** — API rate limiting to prevent abuse on public-facing deployments.
- [ ] **Data retention policies** — Configurable TTL for raw posts, embeddings, and analysis results. Old data should be archived or purged to manage disk usage on long-running deployments.
- [ ] **Health checks & monitoring** — `/health` endpoint with dependency status (PostgreSQL, Redis, Ollama). Prometheus metrics for ingestion rate, queue depth, LLM latency, error rates.
- [ ] **Backup & recovery** — PostgreSQL backup strategy, Redis persistence configuration, disaster recovery runbook.
- [ ] **Kubernetes / Helm chart** — For organizations running Criba in cloud environments. Includes horizontal pod autoscaling for Celery workers based on queue depth.

#### Dashboard Maturity
- [ ] **Saved searches & filters** — Allow users to save filter presets (e.g., "show only Telegram posts with score > 0.8 from last 7 days").
- [ ] **Scheduled reports** — Daily/weekly email or PDF digest summarizing detected campaigns, new narratives, and trending anomalies.
- [ ] **Mobile-responsive layout** — Current dashboard targets desktop. Need responsive breakpoints for tablet/phone access in field deployments.
- [ ] **Dark mode** — For extended monitoring sessions.

---

## License

AGPLv3 — Free to use, modify, and deploy. Derivative works must remain open source.

---

## Philosophy

Criba does not tell you what to think. It shows you the structural patterns behind what you're seeing. A high astroturfing score does not mean the underlying claim is false — it means the *distribution mechanism* is artificial. The truth or falsity of the content itself is a human judgment that this tool explicitly does not make.

---

*Criba: porque la verdad no necesita bots.*
