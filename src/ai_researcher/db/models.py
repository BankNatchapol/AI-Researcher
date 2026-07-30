"""SQLAlchemy Core definitions for the PostgreSQL schema."""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)

metadata = MetaData()

schema_migration = Table(
    "schema_migration",
    metadata,
    Column("version", Integer, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column(
        "applied_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

source = Table(
    "source",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("kind", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default=text("true")),
)

scope = Table(
    "scope",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("include_terms", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("exclude_terms", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("categories", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("date_from", Date),
    Column("date_to", Date),
    Column("per_source_limit", Integer, nullable=False, server_default=text("100")),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

paper = Table(
    "paper",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("doi", Text),
    Column("arxiv_id", Text),
    Column("openalex_id", Text),
    Column("s2_id", Text),
    Column("title", Text, nullable=False),
    Column("abstract", Text),
    Column("published_at", Date),
    Column("venue", Text),
    Column("is_preprint", Boolean, nullable=False, server_default=text("false")),
    Column("oa_status", Text),
    Column("pdf_path", Text),
    Column("tei_xml", Text),
    Column("parse_status", Text, nullable=False, server_default=text("'pending'")),
    Column("parse_error", Text),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    UniqueConstraint("doi", name="uq_paper_doi"),
    UniqueConstraint("arxiv_id", name="uq_paper_arxiv_id"),
)

paper_author = Table(
    "paper_author",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("position", Integer, nullable=False),
    Column("full_name", Text, nullable=False),
)

paper_source = Table(
    "paper_source",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "source_id",
        BigInteger,
        ForeignKey("source.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("external_id", Text, nullable=False),
    Column(
        "retrieved_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

paper_scope = Table(
    "paper_scope",
    metadata,
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "scope_id",
        BigInteger,
        ForeignKey("scope.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

section = Table(
    "section",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "parent_id",
        BigInteger,
        ForeignKey("section.id", ondelete="CASCADE"),
    ),
    Column("section_path", Text, nullable=False),
    Column("title", Text),
    Column("ordinal", Integer, nullable=False),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("char_start", Integer),
    Column("char_end", Integer),
    Column("body_text", Text, nullable=False, server_default=text("''")),
)

ingest_job = Table(
    "ingest_job",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "scope_id",
        BigInteger,
        ForeignKey("scope.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("state", Text, nullable=False),
    Column("papers_found", Integer, nullable=False, server_default=text("0")),
    Column("papers_parsed", Integer, nullable=False, server_default=text("0")),
    Column(
        "started_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("finished_at", DateTime(timezone=True)),
    Column("error", Text),
)

tree_node = Table(
    "tree_node",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "section_id",
        BigInteger,
        ForeignKey("section.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "parent_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
    ),
    Column("node_path", Text, nullable=False),
    Column("title", Text),
    Column("summary", Text, nullable=False),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("depth", Integer, nullable=False),
    Column("tree_schema_version", Text, nullable=False),
    Column("summary_model", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)
Index(
    "ix_tree_node_staleness",
    tree_node.c.paper_id,
    tree_node.c.tree_schema_version,
    tree_node.c.summary_model,
)

retrieval_trace = Table(
    "retrieval_trace",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("question", Text, nullable=False),
    Column(
        "scope_id",
        BigInteger,
        ForeignKey("scope.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "expanded_node_ids",
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'"),
    ),
    Column(
        "selected_node_ids",
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'"),
    ),
    Column("nodes_expanded", Integer, nullable=False),
    Column("stopped_reason", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    CheckConstraint(
        "stopped_reason IN ('sufficient_evidence', 'budget_exhausted', 'no_candidates')",
        name="ck_retrieval_trace_stopped_reason",
    ),
)

claim = Table(
    "claim",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("claim_text", Text, nullable=False),
    Column("normalized_text", Text, nullable=False),
    Column("claim_type", Text, nullable=False),
    Column("subject", Text),
    Column("predicate", Text),
    Column("object_value", Float),
    Column("unit", Text),
    Column(
        "canonical_claim_id",
        BigInteger,
        ForeignKey("claim.id", ondelete="SET NULL"),
    ),
    Column("identity_checked_at", DateTime(timezone=True)),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

claim_extraction_observation = Table(
    "claim_extraction_observation",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "claim_id",
        BigInteger,
        ForeignKey("claim.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("claim_text", Text, nullable=False),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "recorded_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

method = Table(
    "method",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("method_text", Text, nullable=False),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

result = Table(
    "result",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("result_text", Text, nullable=False),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

dataset = Table(
    "dataset",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("dataset_name", Text, nullable=False),
    Column("description", Text),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

metric = Table(
    "metric",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("metric_name", Text, nullable=False),
    Column("object_value", Float),
    Column("unit", Text),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

paper_extraction_state = Table(
    "paper_extraction_state",
    metadata,
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("extraction_model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column(
        "validation_accepted",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "validation_rejected",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "completed_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

claim_evidence = Table(
    "claim_evidence",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "claim_id",
        BigInteger,
        ForeignKey("claim.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tree_node_id",
        BigInteger,
        ForeignKey("tree_node.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("stance", Text, nullable=False),
    Column("rationale_text", Text, nullable=False),
    Column("is_direct", Boolean, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    CheckConstraint(
        "stance IN ('supports', 'refutes', 'mentions')",
        name="ck_claim_evidence_stance",
    ),
)

claim_score = Table(
    "claim_score",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "claim_id",
        BigInteger,
        ForeignKey("claim.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("confidence", Integer, nullable=False),
    Column("evidence_quality", Integer, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column(
        "scored_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

discourse_source = Table(
    "discourse_source",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("kind", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default=text("true")),
    Column("last_polled_at", DateTime(timezone=True)),
)

discourse_item = Table(
    "discourse_item",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "source_id",
        BigInteger,
        ForeignKey("discourse_source.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("external_id", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("title", Text),
    Column("author", Text),
    Column("posted_at", DateTime(timezone=True)),
    Column("score", Integer),
    Column("num_comments", Integer),
    Column(
        "retrieved_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    UniqueConstraint(
        "source_id",
        "external_id",
        name="uq_discourse_item_source_external",
    ),
)

discourse_mention = Table(
    "discourse_mention",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "discourse_item_id",
        BigInteger,
        ForeignKey("discourse_item.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "paper_id",
        BigInteger,
        ForeignKey("paper.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("resolved_by", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    CheckConstraint(
        "resolved_by IN ('arxiv', 'doi')",
        name="ck_discourse_mention_resolved_by",
    ),
)

subscription = Table(
    "subscription",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("kind", Text, nullable=False),
    Column(
        "scope_id",
        BigInteger,
        ForeignKey("scope.id", ondelete="CASCADE"),
    ),
    Column(
        "claim_id",
        BigInteger,
        ForeignKey("claim.id", ondelete="CASCADE"),
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    CheckConstraint(
        "kind IN ('topic', 'claim')",
        name="ck_subscription_kind",
    ),
    CheckConstraint(
        "(scope_id IS NOT NULL AND claim_id IS NULL)"
        " OR (scope_id IS NULL AND claim_id IS NOT NULL)",
        name="ck_subscription_exactly_one_target",
    ),
)

sweep_run = Table(
    "sweep_run",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("kind", Text, nullable=False),
    Column(
        "started_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("finished_at", DateTime(timezone=True)),
    Column("state", Text, nullable=False),
    Column("items_found", Integer, nullable=False, server_default=text("0")),
    Column("error", Text),
    CheckConstraint(
        "kind IN ('evidence', 'discourse')",
        name="ck_sweep_run_kind",
    ),
)

__all__ = [
    "claim",
    "claim_evidence",
    "claim_extraction_observation",
    "claim_score",
    "dataset",
    "discourse_item",
    "discourse_mention",
    "discourse_source",
    "ingest_job",
    "metadata",
    "method",
    "metric",
    "paper",
    "paper_author",
    "paper_extraction_state",
    "paper_scope",
    "paper_source",
    "result",
    "retrieval_trace",
    "schema_migration",
    "scope",
    "section",
    "source",
    "subscription",
    "sweep_run",
    "tree_node",
]
