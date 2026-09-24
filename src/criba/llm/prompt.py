"""Prompt construction for LLM post analysis.

The prompt carries the evidence the ingestion pipeline already computed
(heuristic scores, post metadata, author network activity) so the LLM
weighs real measurements instead of re-deriving them from raw text.
"""

ANALYSIS_PROMPT = """You are a narrative analysis engine. Evaluate the following social media post \
and its evidence for signs of coordinated inauthentic behavior.

Evidence:
{evidence_block}

Post content:
\"{content}\"

Evaluate and respond in JSON:
{{
  "coordination_probability": 0.0,
  "reasoning": "brief explanation",
  "narrative_category": "one of: political_support, political_attack, fear_campaign, fundraising_trigger, distraction, organic",
  "detected_language": "ISO 639-1",
  "talking_points_extracted": ["list", "of", "key", "claims"],
  "recommended_action": "one of: flag_for_review, add_to_cluster, dismiss, escalate"
}}"""

MAX_CONTENT_CHARS = 2000

_EVIDENCE_LABELS = {
    "author_handle": "Author handle",
    "account_age_days": "Author account age (days)",
    "language": "Detected language",
    "copypasta_similarity": "Copypasta similarity score (0-1)",
    "temporal_anomaly": "Temporal anomaly score (0-1)",
    "account_age_flag": "New-account flag (0-1)",
    "composite_score": "Composite heuristic anomaly score (0-1)",
    "interaction_targets": "Author's distinct interaction targets (72h graph)",
    "interaction_weight": "Author's total interaction weight (72h graph)",
    "hashtags": "Post hashtags",
    "mentions": "Post mentions",
    "engagement": "Engagement metrics",
    "media_count": "Attached media count",
    "is_reply": "Is a reply",
    "published_at": "Published at (UTC)",
}


def build_analysis_prompt(source: str, content: str, evidence: dict) -> str:
    """Render the analysis prompt for one post.

    `evidence` is an ordered mapping of field name -> value; keys should
    come from _EVIDENCE_LABELS so the model sees stable, human-readable
    labels. Values are formatted defensively: None renders as "unknown",
    empty collections as "none", floats with three decimals.
    """
    return ANALYSIS_PROMPT.format(
        evidence_block=_format_evidence(source, evidence),
        content=content[:MAX_CONTENT_CHARS],
    )


def _format_evidence(source: str, evidence: dict) -> str:
    lines = [f"- Source: {source}"]
    for key, value in evidence.items():
        label = _EVIDENCE_LABELS.get(key, key.replace("_", " ").capitalize())
        lines.append(f"- {label}: {_format_value(value)}")
    return "\n".join(lines)


def _format_value(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) if value else "none"
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items()) if value else "none"
    return str(value)
