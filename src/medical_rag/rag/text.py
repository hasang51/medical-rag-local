import re

_TOKEN = re.compile(r"[0-9a-zçğıöşü]+")

# Soru kalıbı ve sözlük kalıbı. Ayırt edici tıbbi terimler listede yoktur.
_STOP = frozenset(
    {
        "ve",
        "veya",
        "ile",
        "icin",
        "için",
        "bir",
        "bu",
        "şu",
        "su",
        "o",
        "da",
        "de",
        "ki",
        "mi",
        "mı",
        "mu",
        "mü",
        "ne",
        "nasıl",
        "nasil",
        "nedir",
        "olan",
        "olarak",
        "gibi",
        "daha",
        "en",
        "çok",
        "cok",
        "az",
        "her",
        "diye",
        "göre",
        "gore",
        "kadar",
        "sonra",
        "önce",
        "once",
        "içinde",
        "icinde",
        "üzerine",
        "uzerine",
        "ilgili",
        "hakkında",
        "hakkinda",
        "anlamı",
        "anlami",
        "anlama",
        "gelir",
        "nelerdir",
        "hangi",
        "neden",
        "midir",
        "mudur",
        "mıdır",
        "demektir",
    }
)


def fold(text: str) -> str:
    """Türkçe büyük harfi ASCII casefold'un birleşik noktasından korur."""
    return text.replace("İ", "i").replace("I", "ı").casefold()


def tokenize(text: str) -> list[str]:
    folded = fold(text)
    return [token for token in _TOKEN.findall(folded) if token not in _STOP and len(token) > 1]
