from dataclasses import dataclass
from typing import Protocol

from rank_bm25 import BM25Okapi

from medical_rag.rag.chunker import Chunk
from medical_rag.rag.text import tokenize


@dataclass(frozen=True)
class ScoredChunk:
    id: str
    text: str
    source: str
    score: float


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int) -> list[ScoredChunk]: ...


class Bm25Retriever:
    """Yoğun vektör yok. İkinci model aynı 16 GB'ı paylaşmasın diye kelime örtüşmesi."""

    def __init__(self, chunks: list[Chunk], threshold: float) -> None:
        usable = [(chunk, tokenize(chunk.text)) for chunk in chunks]
        usable = [(chunk, tokens) for chunk, tokens in usable if tokens]
        self._chunks = [chunk for chunk, _ in usable]
        self._threshold = threshold
        self._bm25 = BM25Okapi([tokens for _, tokens in usable]) if usable else None

    def retrieve(self, query: str, top_k: int) -> list[ScoredChunk]:
        if self._bm25 is None or top_k <= 0:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda index: float(scores[index]), reverse=True)
        ranked: list[ScoredChunk] = []
        for index in order[:top_k]:
            score = float(scores[index])
            if score < self._threshold:
                continue
            chunk = self._chunks[index]
            ranked.append(
                ScoredChunk(id=chunk.id, text=chunk.text, source=chunk.source, score=score)
            )
        return ranked
