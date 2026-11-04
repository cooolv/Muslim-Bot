"""طبقات الحماية الشرعية والأمنية.

الطبقة 1: قواعد سريعة (هذا الملف) — تمنع الواضح قبل أي استدعاء للنموذج.
الطبقة 2: فحص بالنموذج (assistant.py) — يلتقط الصيغ الملتفّة.
الطبقة 3: تعليمات نظام صارمة (prompts.py) + رمز كناري لكشف تسريب التعليمات.
الطبقة 4: فحص المخرجات قبل الإرسال.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .arabic import normalize, strip_marks
from .blocklist import (
    EDUCATIONAL,
    HARAM_REQUEST,
    JAILBREAK,
    SEXUAL_SUBSTR,
    SEXUAL_WORDS,
)

_AR = "\u0621-\u064Aa-z0-9"


_JAIL = [re.compile(p, re.I) for p in (normalize(x) for x in JAILBREAK)]
_EDU = re.compile("|".join(normalize(x) for x in EDUCATIONAL))
_HARAM = {c: [re.compile(normalize(p)) for p in ps] for c, ps in HARAM_REQUEST.items()}
_SUBSTR = [normalize(x) for x in SEXUAL_SUBSTR]
_WORDS = [
    re.compile(rf"(?<![{_AR}])[وبلفك]?{re.escape(normalize(w))}(?![{_AR}])")
    for w in SEXUAL_WORDS
]
_SQUASH = re.compile(r"[\s\.\-_*+·•،,;:'\"`~|/\\()\[\]{}]+")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    category: str = "ok"


OK = Verdict(True)

REFUSALS = {
    "sexual": (
        "{n}هذا الموضوع لا أستطيع مساعدتك فيه لأنه مخالف للشريعة 🤍\n"
        "وإن كنت تحاول الابتعاد عن عادة أو محتوى محرم، فأنا معك: اكتب لي «تطبيقات تساعدني على التعافي» "
        "وسأرشح لك ما يناسبك من تطبيقات القناة."
    ),
    "jailbreak": (
        "{n}قواعدي الشرعية ثابتة ولا تتغير، حتى لو جاء الطلب على شكل لعبة أو تمثيل أو اختبار 🙂\n"
        "يسعدني أن أساعدك في أسئلتك الدينية، وترشيح تطبيقات القناة، ومواقيت الصلاة."
    ),
    "haram_request": (
        "{n}هذا الطلب لا أستطيع تنفيذه لأن فيه مخالفة شرعية أو ضررًا 🤍\n"
        "لو أخبرتني بهدفك الأساسي، فقد أقترح لك بديلًا مباحًا ونافعًا."
    ),
    "blasphemy": (
        "{n}لا أستطيع المشاركة في ما فيه استهزاء بالله أو برسوله أو بالدين.\n"
        "أما إن كانت لديك شبهة أو سؤال صادق، فاكتبه وسأجيبك بهدوء واحترام."
    ),
    "fabrication": (
        "{n}لا أستطيع اختلاق أحاديث أو آيات أو فتاوى، فالكذب في الدين أمره عظيم."
    ),
    "output": "{n}عذرًا، لا أستطيع إكمال هذا الرد. جرّب صياغة أخرى لسؤالك 🤍",
    "default": "{n}عذرًا، لا أستطيع المساعدة في هذا الطلب.",
}


def refusal(category: str, name: str = "") -> str:
    n = f"{name}، " if name else ""
    return REFUSALS.get(category, REFUSALS["default"]).format(n=n)


_SPACED = re.compile(r"(?<![\u0621-\u064Aa-z0-9])((?:[\u0621-\u064Aa-z][\s\.\-_*]+){2,}[\u0621-\u064Aa-z])(?![\u0621-\u064Aa-z0-9])")
_JOIN = re.compile(r"[\s\.\-_*]+")


def _collapse_spaced(n: str) -> str:
    """يجمع الحروف المتفرقة مثل «س ك س» أو «p.o.r.n» لكشف التحايل بالمسافات."""
    return _SPACED.sub(lambda m: _JOIN.sub("", m.group(1)), n)


def _is_sexual(n: str) -> bool:
    spaced = _collapse_spaced(n)
    squashed = _SQUASH.sub("", n)
    for t in _SUBSTR:
        if len(t) <= 6:
            if t in n or t in spaced:
                return True
        elif t in squashed:
            return True
    return any(rx.search(n) or rx.search(spaced) for rx in _WORDS)


def check_text(text: str) -> Verdict:
    """فحص سريع بالقواعد لرسالة المستخدم."""
    if not text:
        return OK
    n = normalize(text)
    spaced = _collapse_spaced(n)

    if any(rx.search(n) or rx.search(spaced) for rx in _JAIL):
        return Verdict(False, "jailbreak")

    # السياق التعليمي/العلاجي (سؤال عن حكم، توبة، حجب...) لا يُحجب بالقواعد؛
    # يُترك لفحص النموذج وتعليمات النظام.
    if _EDU.search(n):
        return OK

    if _is_sexual(n):
        return Verdict(False, "sexual")
    for cat, rxs in _HARAM.items():
        if any(rx.search(n) for rx in rxs):
            return Verdict(False, cat if cat in REFUSALS else "haram_request")
    return OK


def is_safe_to_ingest(text: str) -> bool:
    """هل يصلح النص للدخول في قاعدة المعرفة؟ (حماية ضد تسميم المعرفة)."""
    if not check_text(text).allowed:
        return False
    n = normalize(text)
    return not any(rx.search(n) for rx in _JAIL)


# ---------- اسم المستخدم المفضّل ----------
_NAME_OK = re.compile(r"^[\u0621-\u064A\u0670a-zA-Z][\u0621-\u064A\u0670a-zA-Z\s'\-]{0,23}$")


def clean_name(raw: str) -> str | None:
    """ينظّف الاسم ويرفضه إن كان فيه محاولة حقن أو ألفاظ سيئة."""
    name = re.sub(r"\s+", " ", strip_marks(raw or "")).strip(" .,،:;!?؟\"'«»()[]")
    if not name or len(name.split()) > 3 or not _NAME_OK.match(name):
        return None
    if not check_text(name).allowed or not is_safe_to_ingest(name):
        return None
    low = normalize(name)
    if re.search(r"(system|prompt|ignore|instruction|assistant|claude|gpt|تعليمات|نظام|تجاهل|بوت|مساعد)", low):
        return None
    return name


# ---------- فحص المخرجات ----------
def check_output(text: str, canary: str) -> Verdict:
    """فحص الرد قبل إرساله: تسريب التعليمات أو ألفاظ جنسية صريحة."""
    if canary and canary in text:
        return Verdict(False, "output")
    n = normalize(text)
    if any(rx.search(n) for rx in _WORDS):
        return Verdict(False, "output")
    return OK
