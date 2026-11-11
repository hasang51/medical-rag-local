import re
from dataclasses import dataclass

from medical_rag.rag.text import fold

ABSTAIN_TEXT = "Kaynaklarda bu soruyu yanıtlamak için yeterli bilgi yok."
DISCLAIMER = "Bu yanıt eğitim amaçlıdır; tanı, tedavi veya doz önerisi değildir."

# Katlanmış metinde aranır. "tanı koyamam" eşleşmez; "tanınız" eşleşir.
_ROLE = re.compile(r"doktorunuz|tanınız|teşhisim|tedaviniz|\d+\s*mg")


@dataclass(frozen=True)
class Decision:
    answer: str
    citations: list[str]
    abstained: bool


def abstain() -> Decision:
    return Decision(answer=ABSTAIN_TEXT, citations=[], abstained=True)


def enforce_contract(answer: str, allowed_ids: list[str]) -> Decision:
    """Alıntı yoksa veya klinik rol iddiası varsa çekimser metne düş.

    Alıntısız cümle kullanıcıya olduğu gibi gitmez. Böylece değerlendirmede
    alıntısız iddia sayısı sıfır kalır; o kayıt çekimser sayılır.
    """
    folded = fold(answer)
    found = [chunk_id for chunk_id in allowed_ids if chunk_id in answer]
    if _ROLE.search(folded) or not found:
        return abstain()
    return Decision(answer=answer.strip(), citations=found, abstained=False)
