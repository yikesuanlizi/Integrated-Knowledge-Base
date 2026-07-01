from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.models.schemas import Chunk, ChunkMetadata, ParsedBlock, ParsedDocument, ParsedPage


SECTION_HEADER_REGEX = re.compile(
    r"^(#{1,6})\s*(.+)$",
    re.MULTILINE,
)
CHINESE_SECTION_REGEX = re.compile(
    r"^(第[一二三四五六七八九十\d]+[章节篇部])\s*(.+)$",
    re.MULTILINE,
)
PARAGRAPH_REGEX = re.compile(r"\n\s*\n")
BULLET_LIST_REGEX = re.compile(r"^(\s*[-*•●➢→]\s+)", re.MULTILINE)
NUMBERED_LIST_REGEX = re.compile(r"^(\s*\d+[\.\)\、]\s+)", re.MULTILINE)


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 2000
    min_chars: int = 200
    overlap_chars: int = 300
    preserve_section_boundaries: bool = True
    preserve_paragraph_boundaries: bool = True
    preserve_list_boundaries: bool = True
    preserve_block_type: bool = True
    include_section_path: bool = True
    include_page_numbers: bool = True
    include_block_type: bool = True


@dataclass(frozen=True)
class _ChunkAccumulator:
    text: str = ""
    metadata: ChunkMetadata = field(default_factory=lambda: ChunkMetadata())
    page_numbers: set[int] = field(default_factory=set)
    section_path: str | None = None


def chunk_document(document: ParsedDocument, config: ChunkingConfig | None = None) -> list[Chunk]:
    if config is None:
        config = ChunkingConfig()

    chunks: list[Chunk] = []
    if document.blocks:
        chunks.extend(_chunk_from_blocks(document, config))
    else:
        chunks.extend(_chunk_from_pages(document, config))

    return _post_process_chunks(chunks, config)


def _chunk_from_blocks(document: ParsedDocument, config: ChunkingConfig) -> list[Chunk]:
    accumulator = _ChunkAccumulator()
    chunks: list[Chunk] = []

    for block in document.blocks:
        block_text = block.text.strip()
        if not block_text:
            continue

        should_flush = _should_flush_block(accumulator, block, config)

        if should_flush and accumulator.text:
            chunks.append(_finalize_chunk(accumulator, document, config))
            accumulator = _ChunkAccumulator()

        accumulator = _append_block_to_accumulator(accumulator, block, config)

    if accumulator.text:
        chunks.append(_finalize_chunk(accumulator, document, config))

    return chunks


def _chunk_from_pages(document: ParsedDocument, config: ChunkingConfig) -> list[Chunk]:
    all_text = "\n\n".join(page.text for page in document.pages)
    sections = _split_into_sections(all_text)

    accumulator = _ChunkAccumulator()
    chunks: list[Chunk] = []

    for section_index, (section_text, section_header) in enumerate(sections):
        section_parts = _split_section(section_text, config)

        for part_index, part in enumerate(section_parts):
            part_text = part.strip()
            if not part_text:
                continue

            if len(accumulator.text) + len(part_text) > config.max_chars and accumulator.text:
                chunks.append(_finalize_chunk(accumulator, document, config))
                accumulator = _ChunkAccumulator(
                    section_path=section_header,
                )

            accumulator.text += (accumulator.text + "\n\n" if accumulator.text else "") + part_text

            if section_header:
                accumulator.section_path = section_header

    if accumulator.text:
        chunks.append(_finalize_chunk(accumulator, document, config))

    return chunks


def _should_flush_block(accumulator: _ChunkAccumulator, block: ParsedBlock, config: ChunkingConfig) -> bool:
    if not accumulator.text:
        return False

    new_length = len(accumulator.text) + len(block.text)
    if new_length > config.max_chars:
        return True

    if config.preserve_section_boundaries:
        if block.section_path and accumulator.section_path and block.section_path != accumulator.section_path:
            if len(accumulator.text) >= config.min_chars:
                return True

    if config.preserve_block_type:
        if block.block_type in {"title", "section_header"}:
            if len(accumulator.text) >= config.min_chars:
                return True

    return False


def _append_block_to_accumulator(accumulator: _ChunkAccumulator, block: ParsedBlock, config: ChunkingConfig) -> _ChunkAccumulator:
    new_text = accumulator.text + ("\n\n" if accumulator.text else "") + block.text

    new_page_numbers = accumulator.page_numbers.copy()
    if block.page_no:
        new_page_numbers.add(block.page_no)

    new_section_path = accumulator.section_path
    if block.section_path:
        new_section_path = block.section_path

    new_metadata = ChunkMetadata(
        block_type=block.block_type if config.include_block_type else None,
        section_path=new_section_path if config.include_section_path else None,
        page_numbers=sorted(new_page_numbers) if config.include_page_numbers else None,
    )

    return _ChunkAccumulator(
        text=new_text,
        metadata=new_metadata,
        page_numbers=new_page_numbers,
        section_path=new_section_path,
    )


def _finalize_chunk(accumulator: _ChunkAccumulator, document: ParsedDocument, config: ChunkingConfig) -> Chunk:
    text = accumulator.text.strip()

    source_file = str(document.path.name) if document.path else None

    return Chunk(
        content=text,
        source_file=source_file,
        metadata=accumulator.metadata,
        chunk_index=0,
    )


def _split_into_sections(text: str) -> list[tuple[str, str | None]]:
    sections: list[tuple[str, str | None]] = []

    chinese_matches = list(CHINESE_SECTION_REGEX.finditer(text))
    md_matches = list(SECTION_HEADER_REGEX.finditer(text))

    all_matches = []
    for match in chinese_matches:
        all_matches.append((match.start(), match.end(), match.group(1) + " " + match.group(2)))
    for match in md_matches:
        all_matches.append((match.start(), match.end(), match.group(2)))

    all_matches.sort(key=lambda x: x[0])

    last_end = 0
    for start, end, header in all_matches:
        if start > last_end:
            content = text[last_end:start].strip()
            if content:
                sections.append((content, None))
        sections.append((header, header))
        last_end = end

    if last_end < len(text):
        content = text[last_end:].strip()
        if content:
            sections.append((content, None))

    return sections


def _split_section(section_text: str, config: ChunkingConfig) -> list[str]:
    parts: list[str] = []

    if config.preserve_paragraph_boundaries:
        paragraphs = PARAGRAPH_REGEX.split(section_text)
        paragraph_parts = _merge_paragraphs(paragraphs, config)
        parts.extend(paragraph_parts)
    else:
        parts = _split_by_char_count(section_text, config)

    return parts


def _merge_paragraphs(paragraphs: list[str], config: ChunkingConfig) -> list[str]:
    merged: list[str] = []
    current: str = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(current) + len(paragraph) > config.max_chars and current:
            merged.append(current)
            current = paragraph
        else:
            current += (current + "\n\n" if current else "") + paragraph

    if current:
        merged.append(current)

    return merged


def _split_by_char_count(text: str, config: ChunkingConfig) -> list[str]:
    parts: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + config.max_chars, text_length)

        if end < text_length:
            space_pos = text.rfind(" ", start + config.min_chars, end)
            if space_pos != -1:
                end = space_pos

        parts.append(text[start:end].strip())
        start = end - config.overlap_chars

    return parts


def _post_process_chunks(chunks: list[Chunk], config: ChunkingConfig) -> list[Chunk]:
    final_chunks: list[Chunk] = []

    for index, chunk in enumerate(chunks):
        if len(chunk.content) < config.min_chars:
            if final_chunks:
                final_chunks[-1] = Chunk(
                    content=final_chunks[-1].content + "\n\n" + chunk.content,
                    source_file=final_chunks[-1].source_file,
                    metadata=_merge_metadata(final_chunks[-1].metadata, chunk.metadata),
                    chunk_index=final_chunks[-1].chunk_index,
                )
                continue

        chunk = Chunk(
            content=chunk.content,
            source_file=chunk.source_file,
            metadata=chunk.metadata,
            chunk_index=index,
        )
        final_chunks.append(chunk)

    return final_chunks


def _merge_metadata(metadata1: ChunkMetadata, metadata2: ChunkMetadata) -> ChunkMetadata:
    page_numbers = set(metadata1.page_numbers or []) | set(metadata2.page_numbers or [])
    section_path = metadata1.section_path or metadata2.section_path

    return ChunkMetadata(
        block_type=metadata1.block_type,
        section_path=section_path,
        page_numbers=sorted(page_numbers) if page_numbers else None,
    )


def calculate_chunk_hash(chunk: Chunk) -> str:
    import hashlib
    content = chunk.content + (chunk.source_file or "")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunks_to_text(chunks: Iterable[Chunk]) -> str:
    return "\n\n---\n\n".join(chunk.content for chunk in chunks)
