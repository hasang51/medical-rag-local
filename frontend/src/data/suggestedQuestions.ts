/**
 * data/eval/questions.json ve data/corpus/*.md sentetik eğitim derlemiyle sınırlı örnek sorular.
 * Gerçek hasta verisi içermez.
 */

export interface SuggestedQuestion {
  id: string;
  category: string;
  question: string;
  corpusHint: string;
  isOutOfScopeDemo?: boolean;
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
