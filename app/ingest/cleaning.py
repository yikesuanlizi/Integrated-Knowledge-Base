from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CleaningRule:
    name: str
    enabled: bool = True

    def apply(self, text: str) -> str:
        raise NotImplementedError


class RegexSubRule(CleaningRule):
    pattern: re.Pattern[str]
    replacement: str

    def __init__(self, name: str, pattern: str, replacement: str = "", flags: int = 0, enabled: bool = True):
        super().__init__(name=name, enabled=enabled)
        object.__setattr__(self, "pattern", re.compile(pattern, flags))
        object.__setattr__(self, "replacement", replacement)

    def apply(self, text: str) -> str:
        return self.pattern.sub(self.replacement, text)


class FixHyphenationBreaks(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="FixHyphenationBreaks")

    def apply(self, text: str) -> str:
        return re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)


class StripHeadersFooters(CleaningRule):
    _patterns = [
        re.compile(r"^\s*(?:AMM|CMM|SRM|IPC|FIM)\s+[A-Z0-9\-]+\s+Page\s+\d+\s*$", re.IGNORECASE),
        re.compile(r"^\s*(?:AIRBUS|BOEING|EMBRAER|COMAC).{0,80}Page\s+\d+\s*$", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripHeadersFooters")

    def apply(self, text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            if any(pattern.match(line.strip()) for pattern in self._patterns):
                continue
            kept.append(line)
        return "\n".join(kept)


class StripPageNumbers(CleaningRule):
    _patterns = [
        re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
        re.compile(r"^\s*第\s*\d+\s*页\s*(?:共\s*\d+\s*页)?\s*$", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripPageNumbers")

    def apply(self, text: str) -> str:
        lines = [line for line in text.splitlines() if not any(p.match(line.strip()) for p in self._patterns)]
        return "\n".join(lines)


class StripRevisionBanners(CleaningRule):
    _patterns = [
        re.compile(r"\bREV(?:ISION)?\s+\d+\b", re.IGNORECASE),
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripRevisionBanners")

    def apply(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line
            for pattern in self._patterns:
                line = pattern.sub("", line)
            if line.strip(" |-_"):
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)


class StripLegalBoilerplate(CleaningRule):
    _patterns = [
        re.compile(r"CONFIDENTIAL\s*-\s*DO NOT COPY", re.IGNORECASE),
        re.compile(r"ALL RIGHTS RESERVED", re.IGNORECASE),
        re.compile(r"PROPRIETARY INFORMATION", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripLegalBoilerplate")

    def apply(self, text: str) -> str:
        lines = [line for line in text.splitlines() if not any(p.search(line) for p in self._patterns)]
        return "\n".join(lines)


class NormalizeWhitespace(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="NormalizeWhitespace")

    def apply(self, text: str) -> str:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        normalized = "\n".join(lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()


class StripEmptySegments(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="StripEmptySegments")

    def apply(self, text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            compact = re.sub(r"[\W_]+", "", line, flags=re.UNICODE)
            if not line.strip():
                kept.append("")
                continue
            if len(compact) < 3:
                continue
            kept.append(line)
        return "\n".join(kept)


class FixOcrRepetition(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="FixOcrRepetition")

    def apply(self, text: str) -> str:
        return re.sub(r"(.)\1{4,}", lambda m: m.group(1) * 2, text)


class StripOcrGarbage(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="StripOcrGarbage")

    def apply(self, text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                kept.append("")
                continue
            bad_chars = sum(1 for ch in stripped if not (ch.isalnum() or "\u4e00" <= ch <= "\u9fff" or ch in " -_/.,:;()%[]"))
            ratio = bad_chars / max(1, len(stripped))
            if ratio > 0.6:
                continue
            kept.append(line)
        return "\n".join(kept)


class StripTableFragments(CleaningRule):
    _patterns = [
        re.compile(r"^\s*(?:\|\s*){3,}\|?\s*$"),
        re.compile(r"^\s*[─—\-]{2,}(?:[┼+|][─—\-]{2,})+\s*$"),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripTableFragments")

    def apply(self, text: str) -> str:
        lines = [line for line in text.splitlines() if not any(p.match(line.strip()) for p in self._patterns)]
        return "\n".join(lines)


class StripNumberedSpine(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="StripNumberedSpine")

    def apply(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            if re.fullmatch(r"\s*(?:\d+[\.\)]?\s*){2,}\s*", line):
                continue
            lines.append(line)
        return "\n".join(lines)


class StripWeakSentences(CleaningRule):
    _weak_patterns = [
        re.compile(r"this page intentionally left blank", re.IGNORECASE),
        re.compile(r"blank page", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        super().__init__(name="StripWeakSentences")

    def apply(self, text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if any(p.search(stripped) for p in self._weak_patterns):
                continue
            if len(stripped) < 20 and not re.search(r"[\dA-Z]{2,}|ATA|AMM|CMM|SRM", stripped):
                if stripped and re.fullmatch(r"[\w\s\-]+", stripped, re.UNICODE):
                    continue
            kept.append(line)
        return "\n".join(kept)


class MergeSentenceBreaks(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="MergeSentenceBreaks")

    def apply(self, text: str) -> str:
        lines = text.splitlines()
        merged: list[str] = []
        index = 0
        while index < len(lines):
            current = lines[index].strip()
            if not current:
                merged.append("")
                index += 1
                continue

            while index + 1 < len(lines):
                nxt = lines[index + 1].strip()
                if not nxt:
                    break
                if re.search(r"[。！？.!?:;]$", current):
                    break
                current = f"{current} {nxt}"
                index += 1
            merged.append(current)
            index += 1
        return "\n".join(merged)


class DeduplicateBoilerplate(CleaningRule):
    def __init__(self) -> None:
        super().__init__(name="DeduplicateBoilerplate")

    def apply(self, text: str) -> str:
        seen: set[str] = set()
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                kept.append("")
                continue
            canonical = re.sub(r"\s+", " ", stripped).lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            kept.append(stripped)
        return "\n".join(kept)


SEARCH_RULES: list[CleaningRule] = [
    FixHyphenationBreaks(),
    StripHeadersFooters(),
    StripPageNumbers(),
    StripRevisionBanners(),
    StripLegalBoilerplate(),
    NormalizeWhitespace(),
    StripEmptySegments(),
]

EMBEDDING_RULES: list[CleaningRule] = [
    FixOcrRepetition(),
    StripOcrGarbage(),
    StripTableFragments(),
    StripNumberedSpine(),
    StripWeakSentences(),
    MergeSentenceBreaks(),
    DeduplicateBoilerplate(),
]


def _apply_rules(text: str, rules: list[CleaningRule]) -> str:
    current = text or ""
    for rule in rules:
        if rule.enabled:
            current = rule.apply(current)
    return current.strip()


def clean_for_search(raw_content: str) -> str:
    return _apply_rules(raw_content, SEARCH_RULES)


def clean_for_embedding(raw_content: str) -> str:
    search_cleaned = clean_for_search(raw_content)
    return _apply_rules(search_cleaned, EMBEDDING_RULES)
