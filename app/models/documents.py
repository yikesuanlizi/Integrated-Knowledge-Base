from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Build(Base):
    __tablename__ = "builds"

    build_id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    status = Column(String, nullable=False)
    source_path = Column(String)
    force = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSONB, nullable=False, default="{}")
    parser_name = Column(String)
    parser_version = Column(String)
    chunker_version = Column(String, nullable=False, default="paragraph-section-v2")
    wiki_compiler_version = Column(String, nullable=False, default="typed-card-graph-v2")
    document_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    wiki_card_count = Column(Integer, nullable=False, default=0)
    parse_artifact_count = Column(Integer, nullable=False, default=0)
    parse_block_count = Column(Integer, nullable=False, default=0)
    manifest_json = Column(JSONB, nullable=False, default="{}")
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")
    started_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")
    finished_at = Column(String)


class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    file_name = Column(String, nullable=False)
    source_path = Column(String, nullable=False)
    source_hash = Column(String, nullable=False, unique=True)
    manual_type = Column(String)
    aircraft_model = Column(String)
    engine_model = Column(String)
    ata_chapter = Column(String)
    manual_revision = Column(String)
    effective_date = Column(String)
    applicability = Column(String)
    language = Column(String)
    confidentiality = Column(String)
    parser_name = Column(String)
    parser_version = Column(String)
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")

    chunks = relationship("Chunk", back_populates="document")
    wiki_cards = relationship("WikiCard", back_populates="document")


class BuildDocument(Base):
    __tablename__ = "build_documents"

    build_id = Column(String, ForeignKey("builds.build_id"), primary_key=True)
    doc_id = Column(String, ForeignKey("documents.doc_id"), primary_key=True)
    position = Column(Integer, nullable=False, default=0)


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    doc_id = Column(String, ForeignKey("documents.doc_id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    raw_content = Column(Text, nullable=False)
    search_content = Column(Text, nullable=False, default="")
    embedding_content = Column(Text, nullable=False, default="")
    page_start = Column(Integer)
    page_end = Column(Integer)
    section_path = Column(String)
    block_type = Column(String, nullable=False)
    source_ref = Column(String, nullable=False)
    status = Column(String, nullable=False, default="review")
    reviewer = Column(String)
    reviewed_at = Column(String)

    document = relationship("Document", back_populates="chunks")
    wiki_card_chunks = relationship("WikiCardChunk", back_populates="chunk")


class ParseArtifact(Base):
    __tablename__ = "parse_artifacts"

    artifact_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    doc_id = Column(String, ForeignKey("documents.doc_id"), nullable=False)
    parser_name = Column(String, nullable=False)
    parser_version = Column(String)
    source_format = Column(String)
    status = Column(String, nullable=False)
    page_count = Column(Integer, nullable=False, default=0)
    block_count = Column(Integer, nullable=False, default=0)
    raw_json_path = Column(String)
    markdown_path = Column(String)
    artifact_json = Column(JSONB, nullable=False, default="{}")
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")


class ParseBlock(Base):
    __tablename__ = "parse_blocks"

    block_id = Column(String, primary_key=True)
    artifact_id = Column(String, ForeignKey("parse_artifacts.artifact_id"), nullable=False)
    build_id = Column(String, ForeignKey("builds.build_id"))
    doc_id = Column(String, ForeignKey("documents.doc_id"), nullable=False)
    block_index = Column(Integer, nullable=False)
    page_no = Column(Integer)
    block_type = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    section_path = Column(String)
    bbox_json = Column(String)
    table_json = Column(String)
    raw_json = Column(String)
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")


class ChunkParseBlock(Base):
    __tablename__ = "chunk_parse_blocks"

    chunk_id = Column(String, ForeignKey("chunks.chunk_id"), primary_key=True)
    block_id = Column(String, ForeignKey("parse_blocks.block_id"), primary_key=True)
    position = Column(Integer, nullable=False, default=0)
    overlap_score = Column(Float, nullable=False, default=0)


class WikiCard(Base):
    __tablename__ = "wiki_cards"

    card_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    card_type = Column(String, nullable=False)
    doc_id = Column(String, ForeignKey("documents.doc_id"), nullable=False)
    title = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    source_ref = Column(String, nullable=False)
    aircraft_model = Column(String)
    manual_type = Column(String)
    ata_chapter = Column(String)
    manual_revision = Column(String)
    effective_date = Column(String)
    facts_json = Column(JSONB, nullable=False, default="{}")
    linked_entities_json = Column(JSONB, nullable=False, default="[]")
    confidence = Column(Float, nullable=False, default=0.6)
    status = Column(String, nullable=False, default="review")
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")

    document = relationship("Document", back_populates="wiki_cards")
    wiki_card_chunks = relationship("WikiCardChunk", back_populates="wiki_card")
    wiki_claims = relationship("WikiClaim", back_populates="wiki_card")
    wiki_reviews = relationship("WikiReview", back_populates="wiki_card")


class WikiCardChunk(Base):
    __tablename__ = "wiki_card_chunks"

    card_id = Column(String, ForeignKey("wiki_cards.card_id"), primary_key=True)
    chunk_id = Column(String, ForeignKey("chunks.chunk_id"), primary_key=True)
    position = Column(Integer, nullable=False, default=0)

    wiki_card = relationship("WikiCard", back_populates="wiki_card_chunks")
    chunk = relationship("Chunk", back_populates="wiki_card_chunks")


class WikiClaim(Base):
    __tablename__ = "wiki_claims"

    claim_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    card_id = Column(String, ForeignKey("wiki_cards.card_id"), nullable=False)
    doc_id = Column(String, ForeignKey("documents.doc_id"), nullable=False)
    claim_type = Column(String, nullable=False)
    claim_text = Column(Text, nullable=False)
    source_ref = Column(String)
    source_chunk_id = Column(String, ForeignKey("chunks.chunk_id"))
    confidence = Column(Float, nullable=False, default=0.6)
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")

    wiki_card = relationship("WikiCard", back_populates="wiki_claims")


class WikiReview(Base):
    __tablename__ = "wiki_reviews"

    review_id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("builds.build_id"))
    card_id = Column(String, ForeignKey("wiki_cards.card_id"), nullable=False)
    status = Column(String, nullable=False, default="auto_pending")
    reviewer = Column(String, nullable=False, default="system")
    notes = Column(String, nullable=False, default="")
    created_at = Column(String, nullable=False, default="CURRENT_TIMESTAMP")

    wiki_card = relationship("WikiCard", back_populates="wiki_reviews")


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    job_id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    path = Column(String, nullable=False)
    status = Column(String, nullable=False)
    stage = Column(String, nullable=False, default="queued")
    message = Column(String, nullable=False, default="")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    started_at = Column(String)
    finished_at = Column(String)
    result_json = Column(JSONB)
    error = Column(String)
