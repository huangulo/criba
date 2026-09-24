"""Evidence rendering in the LLM analysis prompt."""

from types import SimpleNamespace

import pytest

from criba.llm.prompt import MAX_CONTENT_CHARS, _format_value, build_analysis_prompt
from criba.llm.tasks import _author_network_evidence, _author_topic_history

# The evidence shape llm/tasks.py builds for each post (Post + HeuristicScore
# row plus the author_graph and topic-history queries).
EVIDENCE = {
    "author_handle": "alice.bsky.social",
    "account_age_days": 12,
    "language": "es",
    "author_topics": ["#elecciones", "#petro"],
    "copypasta_similarity": 0.87,
    "temporal_anomaly": 0.42,
    "account_age_flag": 0.9,
    "composite_score": 0.61,
    "interaction_targets": 7,
    "interaction_weight": 19,
    "hashtags": ["#elecciones", "#colombia"],
    "mentions": ["@candidate"],
    "engagement": {"likes": 3, "reposts": 0},
    "media_count": 2,
    "is_reply": True,
    "published_at": "2026-01-01T00:00:00+00:00",
}


def test_prompt_carries_all_evidence_lines():
    prompt = build_analysis_prompt(source="bluesky", content="some post", evidence=EVIDENCE)

    assert "- Source: bluesky" in prompt
    assert "- Author handle: alice.bsky.social" in prompt
    assert "- Author account age (days): 12" in prompt
    assert "- Author's recent topics: #elecciones, #petro" in prompt
    assert "- Copypasta similarity score (0-1): 0.870" in prompt
    assert "- Temporal anomaly score (0-1): 0.420" in prompt
    assert "- New-account flag (0-1): 0.900" in prompt
    assert "- Composite heuristic anomaly score (0-1): 0.610" in prompt
    assert "- Author's distinct interaction targets (72h graph): 7" in prompt
    assert "- Author's total interaction weight (72h graph): 19" in prompt
    assert "- Post hashtags: #elecciones, #colombia" in prompt
    assert "- Post mentions: @candidate" in prompt
    assert "- Engagement metrics: likes=3, reposts=0" in prompt
    assert "- Attached media count: 2" in prompt
    assert "- Is a reply: yes" in prompt


def test_prompt_keeps_the_json_response_contract():
    prompt = build_analysis_prompt(source="reddit", content="some post", evidence=EVIDENCE)

    assert '"coordination_probability"' in prompt
    assert '"narrative_category"' in prompt
    assert '"talking_points_extracted"' in prompt
    assert '"recommended_action"' in prompt
    assert '"{content}"' not in prompt  # braces survived the format() call


def test_prompt_truncates_long_content():
    prompt = build_analysis_prompt(
        source="reddit",
        content="x" * (MAX_CONTENT_CHARS + 100),
        evidence=EVIDENCE,
    )

    assert "x" * MAX_CONTENT_CHARS in prompt
    assert "x" * (MAX_CONTENT_CHARS + 1) not in prompt


def test_missing_evidence_renders_honestly():
    # Unknown values must read as unknown/none, never as a fake measurement
    # (the old prompt hardcoded network_score=0.0 and topic_history="unknown").
    prompt = build_analysis_prompt(
        source="reddit",
        content="some post",
        evidence={
            "author_handle": None,
            "account_age_days": None,
            "author_topics": [],
            "hashtags": [],
            "engagement": {},
            "is_reply": False,
        },
    )

    assert "- Author handle: unknown" in prompt
    assert "- Author account age (days): unknown" in prompt
    assert "- Author's recent topics: none" in prompt
    assert "- Post hashtags: none" in prompt
    assert "- Engagement metrics: none" in prompt
    assert "- Is a reply: no" in prompt


def test_format_value_handles_edge_types():
    assert _format_value(None) == "unknown"
    assert _format_value(True) == "yes"
    assert _format_value(False) == "no"
    assert _format_value(0.5) == "0.500"
    assert _format_value(()) == "none"
    assert _format_value({}) == "none"
    assert _format_value(7) == "7"
    assert _format_value("plain") == "plain"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeResult(self._row)


class _FakePost:
    project_id = "proj-1"
    source = "bluesky"
    author_id = "alice"


@pytest.mark.asyncio
async def test_author_network_evidence_maps_query_row():
    session = _FakeSession((3, 11))

    evidence = await _author_network_evidence(session, _FakePost())

    assert evidence == {"targets": 3, "weight": 11}
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_author_network_evidence_coerces_none_row_to_zeros():
    # No edges for the author: count() gives 0 and sum() coalesces to 0.
    session = _FakeSession((0, 0))

    evidence = await _author_network_evidence(session, _FakePost())

    assert evidence == {"targets": 0, "weight": 0}


class _FakeRowsSession:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return SimpleNamespace(all=lambda: self._rows)


class _FakeTopicPost:
    project_id = "proj-1"
    author_id = "alice"
    published_at = "2026-01-02T00:00:00+00:00"
    id = "post-1"


@pytest.mark.asyncio
async def test_author_topic_history_ranks_hashtags_by_frequency():
    session = _FakeRowsSession([
        (["#a", "#b"],),
        (["#a"],),
        (["#c"],),
        (None,),
    ])

    topics = await _author_topic_history(session, _FakeTopicPost())

    assert topics == ["#a", "#b", "#c"]
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_author_topic_history_returns_empty_for_new_author():
    session = _FakeRowsSession([])

    topics = await _author_topic_history(session, _FakeTopicPost())

    assert topics == []
