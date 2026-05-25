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
```

### Layer 5: API (FastAPI)

```
GET  /api/narratives              — Active narratives, sorted by momentum
GET  /api/narratives/{id}         — Narrative detail with associated posts
GET  /api/narratives/{id}/timeline — Platform bleed timeline
GET  /api/campaigns               — Detected astroturfing campaigns
GET  /api/campaigns/{id}          — Campaign detail with accounts and posts
GET  /api/posts                   — Search/filter posts (source, date, score)
GET  /api/posts/{id}/analysis     — Heuristic + LLM analysis for a post
GET  /api/graph/clusters          — Current network topology clusters
GET  /api/graph/account/{id}      — Interaction graph for a specific account
GET  /api/stats/dashboard         — Aggregate stats for the dashboard
WS   /ws/live                     — WebSocket feed for real-time alerts
```

### Layer 6: Dashboard (Next.js)

**Views:**

1. **Live Feed** — Real-time stream of flagged posts with anomaly scores
2. **Narrative Map** — Bubble chart showing active narratives sized by momentum, colored by platform spread
3. **Campaign Inspector** — Drill-down into detected astroturfing operations showing account clusters, posting timelines, and lexical similarity scores
4. **Network Graph** — Interactive force-directed graph of author interactions, highlighting tight clusters
5. **Timeline** — Platform bleed visualization showing how a narrative jumps from closed to open platforms over time
6. **Source Health** — Monitoring panel for plugin status, ingestion rates, and error logs

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
# Edit .env with your Telegram session, Reddit OAuth, RSS feeds
docker compose up -d
# Access dashboard at http://localhost:3000
# Access API docs at http://localhost:8000/docs
```

---

## Configuration

```yaml
# criba.yml
general:
  language: es            # primary analysis language
  timezone: America/Bogota
  heuristic_threshold: 0.6  # score above this → send to LLM

ollama:
  host: http://localhost:11434
  model: qwen2.5:14b      # or mistral:7b for lower VRAM
  timeout: 30

sources:
  telegram:
    enabled: true
    channels:
      - "@channel_name_1"
      - "@channel_name_2"
    poll_interval: 60      # seconds

  reddit:
    enabled: true
    subreddits:
      - "Colombia"
    poll_interval: 120

  rss:
    enabled: true
    feeds:
      - name: "El Tiempo"
        url: "https://www.eltiempo.com/rss/..."
      - name: "El Espectador"
        url: "https://www.elespectador.com/rss/..."
    poll_interval: 300

  bluesky:
    enabled: false
    keywords: []

  youtube:
    enabled: false
    channels: []

alerts:
  copypasta_threshold: 10    # flag if 10+ similar posts in 72h
  temporal_cluster_min: 5    # flag if 5+ posts in anomalous window
  new_account_days: 7        # flag accounts younger than this
```

---

## Development Phases

### Phase 1: Foundation (Current)
- [ ] Project scaffold (Docker, Celery, Redis, PostgreSQL)
- [ ] Plugin interface definition
- [ ] Telegram plugin (Colombia political channels)
- [ ] RSS plugin (Colombian news outlets)
- [ ] Database schema migration
- [ ] Basic heuristic filters (copypasta, temporal)

### Phase 2: Analysis Engine
- [ ] Ollama integration with analysis prompt
- [ ] Narrative clustering (semantic similarity via pgvector)
- [ ] Network graph construction and community detection
- [ ] Platform bleed tracking

### Phase 3: API & Dashboard
- [ ] FastAPI endpoints
- [ ] WebSocket live feed
- [ ] Next.js dashboard (live feed, narrative map, campaign inspector)
- [ ] Network graph visualization (D3.js)

### Phase 4: Expansion
- [ ] Reddit plugin
- [ ] Bluesky plugin
- [ ] YouTube comments plugin
- [ ] Multi-language support (Portuguese for Brazil, English for US)
- [ ] Alert system (email/webhook on campaign detection)

### Phase 5: Community
- [ ] Plugin development documentation
- [ ] Contributor guidelines
- [ ] Pre-built configurations for common deployments (Colombia, Brazil, US, Mexico)
- [ ] Academic research export formats

---

## License

AGPLv3 — Free to use, modify, and deploy. Derivative works must remain open source.

---

## Philosophy

Criba does not tell you what to think. It shows you the structural patterns behind what you're seeing. A high astroturfing score does not mean the underlying claim is false — it means the *distribution mechanism* is artificial. The truth or falsity of the content itself is a human judgment that this tool explicitly does not make.

---

*Criba: porque la verdad no necesita bots.*
