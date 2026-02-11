from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Page:
    page_num: int
    text: str


@dataclass
class Chunk:
    chunk_id: str
    page: int
    text: str
