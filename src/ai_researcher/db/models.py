"""SQLAlchemy Core definitions for the Phase 1 PostgreSQL tables."""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
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

__all__ = [
    "ingest_job",
    "metadata",
    "paper",
    "paper_author",
    "paper_scope",
    "paper_source",
    "schema_migration",
    "scope",
    "section",
    "source",
]
