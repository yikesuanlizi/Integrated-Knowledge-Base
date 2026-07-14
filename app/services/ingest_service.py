"""文档摄入服务：封装 ingest API 的业务逻辑。"""
from __future__ import annotations

import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.clients.minio_client import minio_client_manager
from app.clients.llm_client import embedding_client
from app.conf.app_config import config
from app.core.database import AsyncSessionLocal, init_database
from app.core.log import logger
from app.ingest.chunking import calculate_chunk_hash, chunk_document
from app.ingest.cleaning import clean_for_embedding, clean_for_search
from app.ingest.entities import extract_entities
from app.ingest.parsers import discover_files, parse_document
from app.models.schemas import Chunk, ChunkMetadata, DocumentMetadata
from app.retrieval.es_repo import ElasticsearchRepository, EntityESRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.compile_service import CompileService


class IngestService:
    """文档摄入服务，封装文件解析、分块、实体提取和存储逻辑。"""

    def __init__(self):
        self._milvus_repo: Optional[MilvusRepository] = None
        self._es_repo: Optional[ElasticsearchRepository] = None
        self._entity_repo: Optional[EntityESRepository] = None

    @property
    def milvus_repo(self) -> MilvusRepository:
        """延迟初始化 Milvus 仓库。"""
        if self._milvus_repo is None:
            self._milvus_repo = MilvusRepository()
        return self._milvus_repo

    @property
    def es_repo(self) -> ElasticsearchRepository:
        """延迟初始化 ES 仓库。"""
        if self._es_repo is None:
            self._es_repo = ElasticsearchRepository()
        return self._es_repo

    @property
    def entity_repo(self) -> EntityESRepository:
        """延迟初始化实体 ES 仓库。"""
        if self._entity_repo is None:
            self._entity_repo = EntityESRepository()
        return self._entity_repo

    async def ingest_file(
        self,
        file_bytes: bytes,
        filename: str,
        metadata: Optional[DocumentMetadata] = None,
    ) -> dict:
        """摄入单个文件。

        Args:
            file_bytes: 文件二进制内容。
            filename: 文件名。
            metadata: 可选的文档元数据覆盖。

        Returns:
            摄入结果 dict，包含 ingested/skipped/failed/documents/build_id。
        """
        temp_dir = Path(tempfile.gettempdir())
        temp_path = temp_dir / f"{uuid.uuid4()}_{filename}"

        try:
            temp_path.write_bytes(file_bytes)

            parsed = parse_document(temp_path)
            if metadata:
                for key, value in metadata.model_dump().items():
                    if value not in (None, ""):
                        setattr(parsed.metadata, key, value)

            chunks = chunk_document(parsed)
            build_id = str(uuid.uuid4())[:16]
            self._store_source_file(build_id, filename, file_bytes)
            self._prepare_chunk_contents(chunks)
            self._prepare_chunk_ids(chunks, build_id)
            chunk_reviews = {chunk.chunk_id: self._auto_review_chunk(chunk) for chunk in chunks}

            await self._store_pg_records(build_id, filename, filename, parsed, chunks, 0, chunk_reviews)
            await self._store_chunks(chunks, build_id, parsed.metadata, chunk_reviews)
            wiki_result = await self._auto_compile_if_needed(build_id)

            return {
                "ingested": 1,
                "skipped": 0,
                "failed": 0,
                "documents": [{
                    "filename": filename,
                    "chunks": len(chunks),
                    "build_id": build_id,
                }],
                "build_id": build_id,
                "wiki": wiki_result,
            }

        except Exception as e:
            logger.error(f"ingest_file failed for {filename}: {e}", exc_info=True)
            return {
                "ingested": 0,
                "skipped": 0,
                "failed": 1,
                "documents": [{
                    "filename": filename,
                    "error": str(e),
                }],
                "build_id": None,
            }
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    async def ingest_directory(
        self,
        path: str,
        force: bool = False,
        metadata: Optional[DocumentMetadata] = None,
        build_id: Optional[str] = None,
    ) -> dict:
        """批量摄入目录。"""
        dir_path = Path(path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        files = discover_files(dir_path)
        if not files:
            raise ValueError(f"No supported files in: {path}")

        actual_build_id = build_id or str(uuid.uuid4())[:16]
        ingested = 0
        failed = 0
        documents = []

        for position, file_path in enumerate(files):
            try:
                parsed = parse_document(file_path)
                if metadata:
                    for key, value in metadata.model_dump().items():
                        if value not in (None, ""):
                            setattr(parsed.metadata, key, value)
                chunks = chunk_document(parsed)
                self._prepare_chunk_contents(chunks)
                self._prepare_chunk_ids(chunks, actual_build_id)
                self._store_source_file(actual_build_id, file_path.name, file_path.read_bytes())
                chunk_reviews = {chunk.chunk_id: self._auto_review_chunk(chunk) for chunk in chunks}
                await self._store_pg_records(actual_build_id, file_path.name, str(file_path), parsed, chunks, position, chunk_reviews)
                await self._store_chunks(chunks, actual_build_id, parsed.metadata, chunk_reviews)
                ingested += 1
                documents.append({
                    "filename": file_path.name,
                    "chunks": len(chunks),
                    "status": "ok",
                })
            except Exception as e:
                failed += 1
                documents.append({
                    "filename": file_path.name,
                    "status": "failed",
                    "error": str(e),
                })
                logger.warning(f"Ingest {file_path.name} failed: {e}")

        wiki_result = await self._auto_compile_if_needed(actual_build_id)

        return {
            "ingested": ingested,
            "skipped": 0,
            "failed": failed,
            "documents": documents,
            "build_id": actual_build_id,
            "wiki": wiki_result,
        }

    async def get_status(self) -> dict:
        """返回当前摄入状态（Milvus 和 ES 中的 chunk 数量）。"""
        try:
            milvus_count = self.milvus_repo.count()
        except Exception as e:
            logger.debug(f"Milvus count failed: {e}")
            milvus_count = 0

        try:
            es_count = await self.es_repo.count()
        except Exception as e:
            logger.debug(f"ES count failed: {e}")
            es_count = 0

        return {
            "milvus_chunks": milvus_count,
            "elasticsearch_chunks": es_count,
        }

    def _store_source_file(self, build_id: str, filename: str, data: bytes) -> None:
        """Best-effort raw source persistence in MinIO."""
        object_name = f"sources/{build_id}/{filename}"
        try:
            minio_client_manager.put_object(object_name, BytesIO(data), len(data))
        except Exception as e:
            logger.warning(f"Store source file to MinIO failed for {object_name}: {e}")

    def _prepare_chunk_ids(self, chunks: list[Chunk], build_id: str) -> None:
        for chunk in chunks:
            chunk.doc_id = build_id
            chunk.chunk_id = calculate_chunk_hash(chunk)

    def _prepare_chunk_contents(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            raw_content = chunk.raw_content or chunk.content or ""
            chunk.raw_content = raw_content
            chunk.search_content = clean_for_search(raw_content)
            chunk.embedding_content = clean_for_embedding(raw_content)
            chunk.content = chunk.raw_content

    def _auto_review_chunk(self, chunk: Chunk) -> dict:
        content = (chunk.raw_content or chunk.content or "").strip()
        block_type = (chunk.metadata.block_type or "").strip().lower()
        section_path = (chunk.metadata.section_path or "").strip()

        reasons: list[str] = []
        status = "approved"

        if block_type == "ocr_text":
            status = "review"
            reasons.append("ocr_text")
        if len(content) < 20:
            status = "review"
            reasons.append("content_too_short")
        if not section_path and block_type not in {"paragraph", "list", "table", "note", "caution", "warning"}:
            status = "review"
            reasons.append("missing_section_path")
        if any(keyword in content for keyword in ["警告", "危险", "注意", "WARNING", "DANGER", "CAUTION"]):
            status = "review"
            reasons.append("safety_keyword")

        return {
            "status": status,
            "reviewer": "system:auto",
            "reviewed_at": datetime.utcnow().isoformat(),
            "reasons": reasons,
        }

    async def _store_pg_records(
        self,
        build_id: str,
        filename: str,
        source_path: str,
        parsed,
        chunks: list[Chunk],
        position: int,
        chunk_reviews: dict[str, dict],
    ) -> None:
        """Persist source document metadata and chunks for the Knowledge UI."""
        try:
            await init_database()
            from sqlalchemy.dialects.postgresql import insert
            from app.models.documents import Build, BuildDocument, Chunk as DbChunk, Document, ParseArtifact, ParseBlock

            now = datetime.utcnow().isoformat()
            doc_id = f"{build_id}:{position}"
            metadata = parsed.metadata
            artifact = parsed.artifact

            async with AsyncSessionLocal() as session:
                build_stmt = insert(Build).values(
                    build_id=build_id,
                    kind="ingest",
                    status="completed",
                    source_path=source_path,
                    force=0,
                    metadata_json={},
                    parser_name=artifact.parser_name,
                    parser_version=artifact.parser_version,
                    chunker_version="paragraph-section-v2",
                    document_count=1,
                    chunk_count=len(chunks),
                    wiki_card_count=0,
                    parse_artifact_count=1,
                    parse_block_count=len(parsed.blocks),
                    manifest_json={},
                    created_at=now,
                    started_at=now,
                    finished_at=now,
                ).on_conflict_do_update(
                    index_elements=["build_id"],
                    set_={
                        "status": "completed",
                        "chunk_count": len(chunks),
                        "parse_block_count": len(parsed.blocks),
                        "finished_at": now,
                    },
                )
                await session.execute(build_stmt)

                document_stmt = insert(Document).values(
                    doc_id=doc_id,
                    build_id=build_id,
                    file_name=filename,
                    source_path=source_path,
                    source_hash=f"{build_id}:{filename}",
                    manual_type=metadata.manual_type,
                    aircraft_model=metadata.aircraft_model,
                    engine_model=metadata.engine_model,
                    ata_chapter=metadata.ata_chapter,
                    manual_revision=metadata.manual_revision,
                    effective_date=metadata.effective_date,
                    applicability=metadata.applicability,
                    language=metadata.language,
                    confidentiality=metadata.confidentiality,
                    parser_name=artifact.parser_name,
                    parser_version=artifact.parser_version,
                    created_at=now,
                ).on_conflict_do_update(
                    index_elements=["doc_id"],
                    set_={
                        "file_name": filename,
                        "source_path": source_path,
                        "parser_name": artifact.parser_name,
                        "parser_version": artifact.parser_version,
                    },
                )
                await session.execute(document_stmt)

                build_doc_stmt = insert(BuildDocument).values(
                    build_id=build_id,
                    doc_id=doc_id,
                    position=position,
                ).on_conflict_do_nothing()
                await session.execute(build_doc_stmt)

                artifact_id = f"{doc_id}:artifact"
                artifact_stmt = insert(ParseArtifact).values(
                    artifact_id=artifact_id,
                    build_id=build_id,
                    doc_id=doc_id,
                    parser_name=artifact.parser_name,
                    parser_version=artifact.parser_version,
                    source_format=artifact.source_format,
                    status=artifact.status,
                    page_count=artifact.page_count,
                    block_count=len(parsed.blocks),
                    raw_json_path="",
                    markdown_path="",
                    artifact_json={
                        "warnings": list(artifact.warnings or ()),
                        "ocr_enabled": artifact.ocr_enabled,
                    },
                    created_at=now,
                ).on_conflict_do_update(
                    index_elements=["artifact_id"],
                    set_={
                        "status": artifact.status,
                        "page_count": artifact.page_count,
                        "block_count": len(parsed.blocks),
                    },
                )
                await session.execute(artifact_stmt)

                for block in parsed.blocks:
                    block_id = f"{doc_id}:block:{block.block_index}"
                    block_stmt = insert(ParseBlock).values(
                        block_id=block_id,
                        artifact_id=artifact_id,
                        build_id=build_id,
                        doc_id=doc_id,
                        block_index=block.block_index,
                        page_no=block.page_no,
                        block_type=block.block_type,
                        text=block.text,
                        section_path=block.section_path,
                        bbox_json=block.bbox_json,
                        table_json=block.table_json,
                        raw_json=block.raw_json,
                        created_at=now,
                    ).on_conflict_do_update(
                        index_elements=["block_id"],
                        set_={
                            "text": block.text,
                            "section_path": block.section_path,
                            "block_type": block.block_type,
                        },
                    )
                    await session.execute(block_stmt)

                for index, chunk in enumerate(chunks):
                    pages = chunk.metadata.page_numbers or []
                    review_info = chunk_reviews.get(chunk.chunk_id, {})
                    chunk_stmt = insert(DbChunk).values(
                        chunk_id=chunk.chunk_id,
                        build_id=build_id,
                        doc_id=doc_id,
                        chunk_index=index,
                        raw_content=chunk.raw_content,
                        search_content=chunk.search_content,
                        embedding_content=chunk.embedding_content,
                        page_start=pages[0] if pages else None,
                        page_end=pages[-1] if pages else None,
                        section_path=chunk.metadata.section_path,
                        block_type=chunk.metadata.block_type or "paragraph",
                        source_ref=f"{filename} | p.{pages[0]}" if pages else filename,
                        status=review_info.get("status", "review"),
                        reviewer=review_info.get("reviewer"),
                        reviewed_at=review_info.get("reviewed_at"),
                    ).on_conflict_do_update(
                        index_elements=["chunk_id"],
                        set_={
                            "raw_content": chunk.raw_content,
                            "search_content": chunk.search_content,
                            "embedding_content": chunk.embedding_content,
                            "section_path": chunk.metadata.section_path,
                            "block_type": chunk.metadata.block_type or "paragraph",
                            "status": review_info.get("status", "review"),
                            "reviewer": review_info.get("reviewer"),
                            "reviewed_at": review_info.get("reviewed_at"),
                        },
                    )
                    await session.execute(chunk_stmt)

                await session.commit()
        except Exception as e:
            logger.warning(f"Store PG ingest records failed for {filename}: {e}", exc_info=True)

    async def create_indices(self) -> None:
        """确保 Milvus 和 ES 索引已创建（MilvusRepository 构造时已 _ensure_collection）。"""
        try:
            await self.es_repo.create_index()
        except Exception as e:
            logger.error(f"Create ES index failed: {e}")
            raise

        try:
            await self.entity_repo.create_index()
        except Exception as e:
            logger.error(f"Create Entity ES index failed: {e}")
            raise

    async def _auto_compile_if_needed(self, build_id: str) -> dict | None:
        """存在 approved chunk 时自动触发 Wiki 编译。"""
        try:
            from app.services.wiki_pg_service import count_pg_rows

            approved_count = await count_pg_rows(
                "chunks",
                "build_id = :build_id AND status = 'approved'",
                {"build_id": build_id},
            )
            if approved_count <= 0:
                return {
                    "status": "skipped",
                    "reason": "no_approved_chunks",
                    "build_id": build_id,
                }
            return await CompileService().compile(build_id=build_id)
        except Exception as e:
            logger.warning(f"Auto compile failed for build {build_id}: {e}", exc_info=True)
            return {
                "status": "failed",
                "build_id": build_id,
                "error": str(e),
            }

    async def _store_chunks(
        self,
        chunks: list[Chunk],
        build_id: str,
        metadata: DocumentMetadata,
        chunk_reviews: dict[str, dict] | None = None,
    ) -> None:
        """内部方法：仅把自动审核通过的 chunks 写入 Milvus + ES + 实体索引。"""
        if not chunks:
            return

        chunk_reviews = chunk_reviews or {chunk.chunk_id: self._auto_review_chunk(chunk) for chunk in chunks}
        approved_chunks = [chunk for chunk in chunks if chunk_reviews.get(chunk.chunk_id, {}).get("status") == "approved"]
        if not approved_chunks:
            return

        await self.es_repo.create_index()
        await self.entity_repo.create_index()

        texts = [c.embedding_content[:8000] for c in approved_chunks]
        try:
            embeddings = await embedding_client.embed(texts)
        except Exception as e:
            logger.warning(f"Batch embedding failed, falling back to per-chunk: {e}")
            embeddings = []
            for t in texts:
                try:
                    embeddings.append(await embedding_client.aembed_text(t))
                except Exception:
                    embeddings.append([0.0] * config.embedding_dimensions)

        # 填充 chunk_id/doc_id 并准备 dict（给 Milvus 写）
        chunk_dicts: list[dict] = []
        for chunk in approved_chunks:
            if not chunk.doc_id:
                chunk.doc_id = build_id
            if not chunk.chunk_id:
                chunk.chunk_id = calculate_chunk_hash(chunk)
            chunk_dicts.append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "raw_content": chunk.raw_content,
                "search_content": chunk.search_content,
                "embedding_content": chunk.embedding_content,
                "content": chunk.raw_content,
                "source_file": chunk.source_file or "",
                "section_path": chunk.metadata.section_path or "",
                "block_type": chunk.metadata.block_type or "",
                "page_numbers": chunk.metadata.page_numbers or [],
                "manual_type": metadata.manual_type or "",
                "ata_chapter": metadata.ata_chapter or "",
                "aircraft_model": metadata.aircraft_model or "",
                "manual_revision": metadata.manual_revision or "",
                "effective_date": metadata.effective_date or "",
                "applicability": metadata.applicability or "",
                "status": chunk_reviews.get(chunk.chunk_id, {}).get("status", "approved"),
            })

        es_chunks: list[dict] = []
        entities_index: dict[str, dict] = {}

        for chunk in approved_chunks:
            es_chunk = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "raw_content": chunk.raw_content,
                "search_content": chunk.search_content,
                "embedding_content": chunk.embedding_content,
                "content": chunk.raw_content,
                "source_file": chunk.source_file or "",
                "section_path": chunk.metadata.section_path or "",
                "block_type": chunk.metadata.block_type or "",
                "page_numbers": chunk.metadata.page_numbers or [],
                "manual_type": metadata.manual_type or "",
                "ata_chapter": metadata.ata_chapter or "",
                "aircraft_model": metadata.aircraft_model or "",
                "manual_revision": metadata.manual_revision or "",
                "effective_date": metadata.effective_date or "",
                "applicability": metadata.applicability or "",
                "status": chunk_reviews.get(chunk.chunk_id, {}).get("status", "approved"),
            }
            es_chunks.append(es_chunk)

            entity_result = extract_entities(chunk.raw_content)
            for entity in entity_result.entities:
                key = f"{entity.entity_type.value}_{entity.value}"
                if key not in entities_index:
                    entities_index[key] = {
                        "entity_type": entity.entity_type.value,
                        "value": entity.value,
                        "chunk_ids": [],
                        "doc_ids": [],
                        "source_files": [],
                        "count": 0,
                    }
                entities_index[key]["chunk_ids"].append(chunk.chunk_id)
                entities_index[key]["doc_ids"].append(build_id)
                if chunk.source_file:
                    entities_index[key]["source_files"].append(chunk.source_file)
                entities_index[key]["count"] += 1

        # Milvus 期望 dict，不是 Chunk dataclass
        self.milvus_repo.insert_chunks(chunk_dicts, embeddings)

        import asyncio
        await asyncio.gather(*[self.es_repo.index_chunk(c) for c in es_chunks])

        if entities_index:
            await asyncio.gather(*[self.entity_repo.index_entity(e) for e in entities_index.values()])
