"""تطبيع النص العربي للبحث (تشكيل، همزات، تاء مربوطة، أرقام هندية...)."""
from __future__ import annotations

import re
import unicodedata

_DIAC = re.compile(
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640"
    "\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MAP = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ی": "ي",
        "ؤ": "و", "ة": "ه",
        "ک": "ك", "گ": "ك", "پ": "ب", "چ": "ج", "ڤ": "ف",
    }
)
_SPLIT = re.compile(r"[^\u0621-\u064Aa-z0-9]+")

STOPWORDS = frozenset(
    """
    في من علي الي عن مع ما ماذا هل كيف ليه لماذا ايه ازاي امتي فين مين ده دي دا هذا هذه ذلك
    هو هي انا انت انتم نحن لو لا نعم يا او و ثم كل بعض اي اللي الذي التي كان كانت يكون
    عايز عاوز اريد ابغي ابي محتاج ممكن لازم يعني بس كمان برضو جدا قوي شويه
    تطبيق تطبيقات برنامج حاجه شي شيء
    the a an is are of to for and or in on
    """.split()
)


def normalize(text: str) -> str:
    """تطبيع خفيف: يحافظ على حدود الكلمات."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _DIAC.sub("", text).translate(_DIGITS).translate(_MAP)
    return text.lower()


def strip_marks(text: str) -> str:
    """يشيل التشكيل والتطويل فقط (يحافظ على الحروف الأصلية)."""
    return _DIAC.sub("", unicodedata.normalize("NFKC", text or ""))


def words(text: str) -> list[str]:
    return [w for w in _SPLIT.split(normalize(text)) if w]


_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")


def stem(w: str) -> str:
    for p in _PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 3:
            w = w[len(p):]
            break
    for s in ("ات", "ون", "ين"):
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[: -len(s)]
            break
    return w


def index_text(text: str) -> str:
    """النص الذي يُخزَّن في فهرس البحث."""
    return " ".join(stem(w) for w in words(text))


def query_tokens(text: str, limit: int = 12) -> list[str]:
    seen: list[str] = []
    for w in words(text):
        if w in STOPWORDS:
            continue
        s = stem(w)
        if len(s) >= 2 and s not in seen and s not in STOPWORDS:
            seen.append(s)
    return seen[:limit]


def fts_query(tokens: list[str]) -> str:
    parts = []
    for t in tokens:
        if not t:
            continue
        parts.append(f'"{t}"*' if len(t) >= 3 else f'"{t}"')
    return " OR ".join(parts)
