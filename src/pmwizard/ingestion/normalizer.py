"""Deterministic source normalization and hashing."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict


class NormalizedContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_text: str
    excerpt: str
    content_hash: str


class EvidenceContentNormalizer:
    """Normalize source text without interpreting its meaning."""

    def __init__(self, *, max_excerpt_chars: int = 12000) -> None:
        if type(max_excerpt_chars) is not int or max_excerpt_chars < 1:
            raise ValueError("max_excerpt_chars must be a positive integer")
        self.max_excerpt_chars = max_excerpt_chars

    def normalize(self, content: str) -> NormalizedContent:
        text = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]

        collapsed: list[str] = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank and collapsed:
                    collapsed.append("")
                previous_blank = True
                continue
            collapsed.append(line)
            previous_blank = False

        full_text = "\n".join(collapsed).strip()
        digest = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        excerpt = full_text[: self.max_excerpt_chars]

        return NormalizedContent(
            full_text=full_text,
            excerpt=excerpt,
            content_hash=digest,
        )
