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


# Digital Twin modunda hastanın kendi CCO kaydındaki mevcut mg/dL veya reçete adını
# kanıtla aktarmasına izin verilir; ancak doktor rolü, tanı koyma ve doz/reçete talimatı engellenir.
_TWIN_ROLE = re.compile(
    r"doktorunuz(?:um| olarak)?(?![a-zçğıöşü])"
    r"|tanınız|teşhisim|tedaviniz"
    r"|kesin\s+olarak\s+.{1,25}\s+hastalığınız\s+var"
    r"|size\s+.{1,30}\s+reçete\s+ediyorum"
    r"|\d+\s*(?:mg|mcg|ml|tablet|damla)\s*(?:alın|almalısınız|kullanın|kullanmalısınız|başlayın|için)"
)


def enforce_twin_contract(answer: str, allowed_ids: list[str]) -> Decision:
    """Digital Twin yanıtında izinli katman alıntısını ve klinik rol sınırını doğrular."""
    folded = fold(answer)
    found = [cid for cid in allowed_ids if cid in answer]
    role_blocked = bool(_TWIN_ROLE.search(folded))
    role_span = _TWIN_ROLE.search(folded)
    history_turn = any("HISTORY-SCOPE" in cid for cid in allowed_ids)
    cited_empty = any("HISTORY-EMPTY" in cid and cid in answer for cid in allowed_ids)
    absence = any(
        token in folded
        for token in (
            "bulunmamaktadır",
            "bulunmuyor",
            "saptanmamıştır",
            "saptanmamistir",
            "saptanmamakta",
            "yoktur",
            "yer almıyor",
            "yer almiyor",
        )
    )
    unsupported_absence = history_turn and absence and not cited_empty
    # #region agent log
    try:
        import json as _json
        import time as _time

        with open(
            r"c:\Projects\medical-rag-local\.cursor\debug-36fe44.log",
            "a",
            encoding="utf-8",
        ) as _fh:
            _fh.write(
                _json.dumps(
                    {
                        "sessionId": "36fe44",
                        "hypothesisId": "V",
                        "location": "policy.py:enforce_twin_contract",
                        "message": "twin contract decision",
                        "data": {
                            "roleBlocked": role_blocked,
                            "roleSpan": role_span.group(0) if role_span else "",
                            "citationFound": bool(found),
                            "found": found,
                            "historyTurn": history_turn,
                            "citedEmpty": cited_empty,
                            "absence": absence,
                            "unsupportedAbsence": unsupported_absence,
                            "reject": bool(role_blocked or not found or unsupported_absence),
                            "rawAnswer": answer[:1200],
                        },
                        "timestamp": int(_time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    if role_blocked or not found or unsupported_absence:
        return abstain()
    return Decision(answer=answer.strip(), citations=found, abstained=False)
