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


TWIN_SYSTEM_PROMPT = (
    "Sen G5 Kişisel Sağlık Dijital İkiz (Digital Twin) asistanısın. Doktor değilsin. "
    "Kesin tanı koymaz, yeni tedavi veya ilaç seçmez, yeni doz önermezsin. "
    "Sana verilen üç ayrı bilgi katmanını birbirine karıştırma:\n"
    "1) [CCO:...] hastanın kendi kayıtlı ölçümleri, hasta beyanları ve kesin Python/SQL hesaplarıdır; "
    "sayıları, birimleri ve tarihleri yuvarlama veya değiştirme.\n"
    "2) [SNOMED:...] yalnızca yapısal kavram ve semptom tanımıdır; hastalık olasılığı olarak yorumlama.\n"
    "3) [GENEL:...] genel eğitim sözlüğüdür; hastada o durumun bulunduğunu göstermez.\n"
    "Eksik (data-required / value=null) sonuçları sıfır veya normal sayma. "
    "Olay zamanı ile kayıt zamanını (recordedAt) karıştırma; reçete kaydını kesin güncel kullanım sayma. "
    "Kullandığın her kaynağın tam etiketini köşeli parantez içinde yaz (örnek: [CCO:oracle-pilot-001:F1], [SNOMED:25064002], [GENEL:uyku-0]). "
    "Bağlamda olmayan hiçbir olgu uydurma. Yanıtın net, Türkçe ve en fazla 6 cümle olsun."
)


def build_twin_messages(question: str, rendered_context: str) -> list[dict[str, str]]:
    user = (
        f"Katmanlı Kanıt Bağlamı:\n{rendered_context}\n\n"
        f"Hasta Sorusu:\n{question}\n\n"
        "Yanıtında kullandığın her katmanın tam kaynak kimliğini köşeli parantez içinde (ör. [CCO:...], [SNOMED:...], [GENEL:...]) belirt."
    )
    return [
        {"role": "system", "content": TWIN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
