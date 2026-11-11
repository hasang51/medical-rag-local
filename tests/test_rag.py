import json

import pytest

from medical_rag.config import Settings
from medical_rag.rag.chunker import chunk_text, load_chunks
from medical_rag.rag.prompt import SYSTEM_PROMPT, build_messages
from medical_rag.rag.retriever import Bm25Retriever, ScoredChunk
from medical_rag.safety.policy import ABSTAIN_TEXT, enforce_contract


def test_chunk_windows_are_fixed() -> None:
    assert chunk_text("   ", 10, 0) == []
    assert chunk_text("kisa metin", 50, 0) == ["kisa metin"]
    parts = chunk_text("abcdefghij", 4, 0)
    assert parts == ["abcd", "efgh", "ij"]
    overlapped = chunk_text("abcdefghij", 4, 1)
    assert overlapped[0] == "abcd"
    assert overlapped[1].startswith("d")
    with pytest.raises(ValueError):
        chunk_text("abc", 4, 4)


def test_corpus_has_at_least_twenty_single_chunks() -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    assert len(chunks) >= 20
    assert all(chunk.id.endswith("-0") for chunk in chunks)
    assert all(len(chunk.text) <= settings.chunk_size for chunk in chunks)


def test_retrieval_fixture() -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)
    cases = json.loads(settings.questions_path.read_text(encoding="utf-8"))
    positives = [case for case in cases if case["expect_hit"]]
    negatives = [case for case in cases if not case["expect_hit"]]
    assert len(positives) == 10
    assert len(negatives) == 2

    misses = []
    for case in positives:
        found = retriever.retrieve(case["question"], 3)
        ids = [item.id for item in found]
        if case["expected_chunk_id"] not in ids:
            misses.append({"id": case["id"], "ids": ids})
    assert len(positives) - len(misses) >= 8, misses

    for case in negatives:
        assert retriever.retrieve(case["question"], 3) == [], case["id"]


def test_prompt_carries_citation_and_refuses_the_clinician_role() -> None:
    chunk = ScoredChunk(id="nabiz-0", text="Nabız bir dalgadır.", source="nabiz.md", score=2.0)
    messages = build_messages("Nabız nedir?", [chunk])
    assert messages[0]["role"] == "system"
    assert "Doktor değilsin" in messages[0]["content"]
    assert SYSTEM_PROMPT in messages[0]["content"]
    assert "[nabiz-0]" in messages[1]["content"]
    assert "Nabız nedir?" in messages[1]["content"]


def test_policy_abstains_without_citation_or_with_a_role_claim() -> None:
    kept = enforce_contract("Nabız dalgadır [nabiz-0].", ["nabiz-0"])
    assert kept.abstained is False
    assert kept.citations == ["nabiz-0"]

    missing = enforce_contract("Emin değilim.", ["nabiz-0"])
    assert missing.abstained is True
    assert missing.answer == ABSTAIN_TEXT

    role = enforce_contract("[nabiz-0] Doktorunuz olarak yazıyorum.", ["nabiz-0"])
    assert role.abstained is True


def test_empty_query_retrieves_nothing() -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)
    assert retriever.retrieve("ne nedir mi", 3) == []
