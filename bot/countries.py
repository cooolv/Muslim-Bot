"""الدول الشائعة + طريقة حساب المواقيت الافتراضية لكل دولة (أرقام Aladhan API).

عدّل الأرقام هنا بسهولة إن أردت طريقة حساب مختلفة. قائمة الطرق الرسمية:
https://aladhan.com/calculation-methods
"""
from __future__ import annotations

from .arabic import normalize

# (ISO, الاسم بالعربية, الاسم بالإنجليزية, رقم الطريقة)
COUNTRIES: list[tuple[str, str, str, int]] = [
    ("EG", "مصر", "Egypt", 5),
    ("SA", "السعودية", "Saudi Arabia", 4),
    ("AE", "الإمارات", "United Arab Emirates", 8),
    ("KW", "الكويت", "Kuwait", 9),
    ("QA", "قطر", "Qatar", 10),
    ("BH", "البحرين", "Bahrain", 8),
    ("OM", "عُمان", "Oman", 8),
    ("JO", "الأردن", "Jordan", 23),
    ("PS", "فلسطين", "Palestine", 3),
    ("LB", "لبنان", "Lebanon", 3),
    ("SY", "سوريا", "Syria", 3),
    ("IQ", "العراق", "Iraq", 3),
    ("YE", "اليمن", "Yemen", 3),
    ("SD", "السودان", "Sudan", 5),
    ("LY", "ليبيا", "Libya", 5),
    ("TN", "تونس", "Tunisia", 18),
    ("DZ", "الجزائر", "Algeria", 19),
    ("MA", "المغرب", "Morocco", 21),
    ("TR", "تركيا", "Turkey", 13),
    ("PK", "باكستان", "Pakistan", 1),
    ("MY", "ماليزيا", "Malaysia", 17),
    ("ID", "إندونيسيا", "Indonesia", 20),
    ("GB", "بريطانيا", "United Kingdom", 3),
    ("US", "أمريكا", "United States", 2),
    ("CA", "كندا", "Canada", 2),
    ("DE", "ألمانيا", "Germany", 3),
    ("FR", "فرنسا", "France", 12),
]
DEFAULT_METHOD = 3  # رابطة العالم الإسلامي

_BY_CODE = {c[0]: c for c in COUNTRIES}


def by_code(code: str) -> tuple[str, str, str, int] | None:
    return _BY_CODE.get((code or "").upper())


def find_country(text: str) -> tuple[str, str, str, int] | None:
    """يطابق اسم دولة مكتوب بالعربية أو الإنجليزية."""
    t = normalize(text).strip()
    for c in COUNTRIES:
        if t in (normalize(c[1]), c[2].lower(), c[0].lower()):
            return c
    return None
