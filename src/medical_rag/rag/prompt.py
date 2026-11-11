from medical_rag.rag.retriever import ScoredChunk

SYSTEM_PROMPT = (
    "Sen eğitim amaçlı bir sözlük asistanısın. Doktor değilsin. "
    "Tanı koymaz, tedavi seçmez, doz söylemezsin. "
    "Yalnızca aşağıda verilen bağlam parçalarındaki cümleleri kullan. "
    "Kullandığın her parçanın kimliğini köşeli parantezle yaz. Örnek: [kan-basinci-0]. "
    "Bağlamda yoksa yeni olgu uydurma. En fazla üç cümle yaz."
)


def build_messages(question: str, chunks: list[ScoredChunk]) -> list[dict[str, str]]:
    blocks = "\n\n".join(f"[{chunk.id}]\n{chunk.text}" for chunk in chunks)
    user = (
        f"Bağlam:\n{blocks}\n\n"
        f"Soru:\n{question}\n\n"
        "Yanıtın, kullandığın parça kimliğini köşeli parantez içinde içersin."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
