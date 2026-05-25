ANALYSIS_PROMPT = """You are a narrative analysis engine. Evaluate the following social media post \
and its metadata for signs of coordinated inauthentic behavior.

Context:
- Source: {source}
- Author account age: {account_age_days} days
- Author's previous topics: {topic_history}
- Heuristic anomaly score: {anomaly_score}
- Similar posts in last 72h: {copypasta_count}
- Temporal anomaly: {temporal_flag}
- Network cluster score: {network_score}

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


def build_analysis_prompt(
    source: str,
    content: str,
    account_age_days: int | None = None,
    topic_history: str = "unknown",
    anomaly_score: float = 0.0,
    copypasta_count: int = 0,
    temporal_flag: bool = False,
    network_score: float = 0.0,
) -> str:
    return ANALYSIS_PROMPT.format(
        source=source,
        account_age_days=account_age_days or 0,
        topic_history=topic_history,
        anomaly_score=round(anomaly_score, 3),
        copypasta_count=copypasta_count,
        temporal_flag=str(temporal_flag),
        network_score=round(network_score, 3),
        content=content[:2000],
    )
