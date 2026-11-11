"""Çalışma zamanı ayarları.

Sayılar keyfi değildir. 16 GB RAM ve CPU-only makinede KV önbelleği
bağlam uzunluğuyla büyür; model kartındaki 128K bu makine için kullanılamaz.
"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
_LOOPBACK = frozenset({"127.0.0.1", "localhost"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDICAL_RAG_",
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Yalnızca loopback. 0.0.0.0 sorguyu makine dışına açar.
    ollama_base_url: str = "http://127.0.0.1:11434"
    # gemma4:latest bugün E4B'ye işaret eder; etiket kaymasın diye sabitlenir.
    model: str = "gemma4:e4b"
    # İlan edilen bağlam 128K. Bu makinede güvenli tavan 2048'dir.
    num_ctx: int = 2048
    # Gemma 4 genel sohbet önerisi temperature=1.0, top_p=0.95, top_k=64.
    # Kaynağa bağlı yanıtta uydurmayı azaltmak için temperature bilinçli olarak 0.2.
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 64
    # Gemma 4 Ollama'da düşünme kanalını açar. think alanı gönderilmezse
    # token bütçesi yanıttan önce düşünmeye gider. RAG turunda kapalıdır.
    # Karşılaştırma için MEDICAL_RAG_THINK=true yazılabilir.
    think: bool = False
    # Kısa yanıt. 512'lik eski tavan karşılaştırma turunda
    # MEDICAL_RAG_NUM_PREDICT=512 ile açılır.
    num_predict: int = 128
    smoke_num_predict: int = 64
    # CPU'da E4B turu onlarca saniye sürebilir.
    request_timeout_seconds: float = 180.0
    health_timeout_seconds: float = 2.0
    # Model yüklü kalsın; her turda yeniden yüklemek RAM'i ve süreyi şişirir.
    keep_alive: str = "30m"
    default_top_k: int = 3
    max_top_k: int = 5
    max_question_chars: int = 500
    # Kısa sözlükte ilgili soru skoru 1'in üstünde, kelime örtüşmesi olmayan soru 0'dır.
    bm25_score_threshold: float = 1.0
    chunk_size: int = 600
    chunk_overlap: int = 0
    corpus_dir: Path = Field(default_factory=lambda: ROOT / "data" / "corpus")
    questions_path: Path = Field(default_factory=lambda: ROOT / "data" / "eval" / "questions.json")
    runtime_dir: Path = Field(default_factory=lambda: ROOT / "data" / "runtime")

    @model_validator(mode="after")
    def ollama_stays_on_loopback(self) -> "Settings":
        host = urlparse(self.ollama_base_url).hostname
        if host not in _LOOPBACK:
            raise ValueError("Ollama adresi yalnızca 127.0.0.1 veya localhost olabilir")
        return self
