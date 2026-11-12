/**
 * Genel eğitim derlemi ve G5 Digital Twin örnek soruları.
 * Ham hasta kimliği veya kişisel sağlık verisi içermez.
 */

export interface SuggestedQuestion {
  id: string;
  category: string;
  question: string;
  corpusHint: string;
  isOutOfScopeDemo?: boolean;
  isEmergencyDemo?: boolean;
}

export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    id: "q01",
    category: "Kardiyovasküler",
    question: "Sistolik ve diyastolik kan basıncı ne anlatır?",
    corpusHint: "kan-basinci-0",
  },
  {
    id: "q06",
    category: "Metabolizma",
    question: "Diyabet glikoz tip 1 ve tip 2 ne demektir?",
    corpusHint: "diyabet-0",
  },
  {
    id: "q07",
    category: "Solunum",
    question: "Astım hırıltı ve bronş daralması ne demektir?",
    corpusHint: "astim-0",
  },
  {
    id: "q05",
    category: "Bağışıklama",
    question: "Aşı antijen ve bağışıklama ne demektir?",
    corpusHint: "asi-0",
  },
  {
    id: "q09",
    category: "Solunum Anatomisi",
    question: "Alveol ve soluk borusu ne işe yarar?",
    corpusHint: "solunum-0",
  },
  {
    id: "q10",
    category: "Sindirim",
    question: "Peristaltizm mide ve ince bağırsak ne demektir?",
    corpusHint: "sindirim-0",
  },
  {
    id: "q08",
    category: "Hematoloji",
    question: "ABO ve Rh alyuvar belirteçleri neyi ayırır?",
    corpusHint: "kan-gruplari-0",
  },
  {
    id: "q11",
    category: "Güvenli Çekimserlik Testi",
    question: "İstanbul'da yarın hava durumu nasıl olacak?",
    corpusHint: "Kapsam dışı • BM25 eşik altı",
    isOutOfScopeDemo: true,
  },
];

export const TWIN_SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    id: "twin-q1",
    category: "1. Kesin Uyku & Eksik HRV Analizi",
    question:
      "Son ana uykum kaç dakika sürdü, 7 günlük uyku ortalamam nedir ve günlük HRV kişisel bazal değerim neden görünmüyor?",
    corpusHint: "SQL/Python kesin hesap • data-required nedeni",
  },
  {
    id: "twin-q2",
    category: "2. Semptom (SNOMED 25064002) + CCO",
    question:
      "Başım ağrıyor; kişisel kayıtlarımda son uyku düzenim, kalp/HRV ölçümlerim veya kayıtlı tanı ve ilaçlarım açısından hangi veriler var?",
    corpusHint: "CCO + SNOMED Headache + Genel 3 katman",
  },
  {
    id: "twin-q3",
    category: "3. Model Öncesi Acil Durum Kapısı",
    question:
      "Göğsümde baskı tarzında şiddetli ağrı, sol koluma yayılan uyuşma ve nefes darlığı başladı; yüzükteki nabzım normal görünüyor, beklemeli miyim?",
    corpusHint: "Pre-LLM 112 Kırmızı Bayrak • Model çağrılmaz",
    isEmergencyDemo: true,
  },
  {
    id: "twin-q4",
    category: "Laboratuvar & İlaç Kayıtları",
    question:
      "Kayıtlarımda son laboratuvar tahlillerim, kayıtlı tanılarım ve reçete/beyan ilaçlarım nelerdir?",
    corpusHint: "CCO lab • diagnosis • medication • hasta beyanı",
  },
];
