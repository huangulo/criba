import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_handle: Mapped[str | None] = mapped_column(String(255))
    author_created: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    engagement: Mapped[dict] = mapped_column(JSONB, default=dict)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    mentions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    reply_to: Mapped[str | None] = mapped_column(String(255))
    raw_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (UniqueConstraint("source", "source_id"),)


class HeuristicScore(Base):
    __tablename__ = "heuristic_scores"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True
    )
    copypasta_score: Mapped[float] = mapped_column(Float, default=0.0)
    temporal_anomaly: Mapped[float] = mapped_column(Float, default=0.0)
    account_age_flag: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    sent_to_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    scored_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LlmAnalysis(Base):
    __tablename__ = "llm_analysis"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True
    )
    coordination_probability: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)
    narrative_category: Mapped[str | None] = mapped_column(String(50))
    talking_points: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    recommended_action: Mapped[str | None] = mapped_column(String(50))
    model_used: Mapped[str | None] = mapped_column(String(100))
    analyzed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Narrative(Base):
    __tablename__ = "narratives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str | None] = mapped_column(String(255))
    first_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    platform_spread: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="active")
    embedding = mapped_column(Vector(768), nullable=True)


class NarrativePost(Base):
    __tablename__ = "narrative_posts"

    narrative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narratives.id"), primary_key=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True
    )


class AuthorGraph(Base):
    __tablename__ = "author_graph"

    source_author: Mapped[str] = mapped_column(String(255), primary_key=True)
    target_author: Mapped[str] = mapped_column(String(255), primary_key=True)
    interaction: Mapped[str] = mapped_column(String(50), primary_key=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    account_count: Mapped[int | None] = mapped_column(Integer)
    post_count: Mapped[int | None] = mapped_column(Integer)
    platforms: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(String(50), default="active")


class PostEmbedding(Base):
    __tablename__ = "post_embeddings"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True
    )
    embedding = mapped_column(Vector(768), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False, default="nomic-embed-text")
    embedded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
