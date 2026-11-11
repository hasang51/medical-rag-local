from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Sabit karakter penceresi. Kelime sınırına yaslanmaz; test tekrarlanabilir kalsın."""
    if size <= 0:
        raise ValueError("chunk_size pozitif olmalı")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap 0 ile chunk_size arasında olmalı")
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    step = size - overlap
    pieces: list[str] = []
    start = 0
    while start < len(cleaned):
        piece = cleaned[start : start + size].strip()
        if piece:
            pieces.append(piece)
        if start + size >= len(cleaned):
            break
        start += step
    return pieces


def load_chunks(directory: Path, size: int, overlap: int) -> list[Chunk]:
    if not directory.is_dir():
        return []
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        for index, piece in enumerate(chunk_text(path.read_text(encoding="utf-8"), size, overlap)):
            chunks.append(Chunk(id=f"{path.stem}-{index}", text=piece, source=path.name))
    return chunks
