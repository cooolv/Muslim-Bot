"""أوامر وتفاعلات تيليجرام."""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from . import guard, knowledge
from .arabic import normalize
from .countries import COUNTRIES, DEFAULT_METHOD, by_code, find_country
from .prayer import PRAYERS, due_prayers, hm, reminder_text

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- أدوات
def _s(ctx):  # الإعدادات
    return ctx.bot_data["settings"]


def _db(ctx):
    return ctx.bot_data["db"]


def _name(u) -> str:
    return (u["preferred_name"] or "").strip() if u else ""


_hits: dict[int, deque] = defaultdict(deque)


def rate_limited(uid: int, per_minute: int) -> bool:
    now = time.time()
    q = _hits[uid]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_minute:
        return True
    q.append(now)
    return False


async def send_long(update: Update, text: str) -> None:
    for i in range(0, len(text), 3900):
        await update.effective_message.reply_text(text[i : i + 3900], disable_web_page_preview=True)


_TRIGGERS = [
    ("انا", "اسمي"), ("اسمي",), ("نادني",), ("ناديني",), ("عايزك", "تناديني"), ("عاوزك", "تناديني"),
    ("خليك", "تناديني"), ("ممكن", "تناديني"), ("my", "name", "is"), ("call", "me"),
]
_NOT_NAMES = {"ايه", "ايش", "شو", "مين", "اي", "كيف", "ازاي", "ليه", "ماذا", "لماذا", "فين"}


def extract_name(text: str) -> str | None:
    """يلتقط الاسم من جمل مثل: «نادني أحمد» / «اسمي محمد» / «call me Sam»."""
    if "?" in text or "؟" in text:
        return None
    ws = text.split()
    nws = [normalize(w) for w in ws]
    for trig in sorted(_TRIGGERS, key=len, reverse=True):
        if tuple(nws[: len(trig)]) == trig:
            rest = ws[len(trig):]
            while rest and normalize(rest[0]) in ("يا", "ب", "باسم", "هو", "is"):
                rest = rest[1:]
            if 1 <= len(rest) <= 3:
                name = guard.clean_name(" ".join(rest))
                if name and normalize(name) not in _NOT_NAMES:
                    return name
    return None


# ---------------------------------------------------------------- نصوص
WELCOME_NEW = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n"
    "أنا {bot}، مساعد ذكي ومجاني أعرف محتوى قناة «تطبيقات المسلم» وأساعدك في أسئلتك وترشيح التطبيقات النافعة، "
    "وأذكّرك بمواقيت الصلاة.\n\n"
    "قبل أن نبدأ: بأي اسم تحب أن أناديك؟ اكتبه الآن (أو أرسل /skip للتخطي)."
)
HELP = (
    "ما يمكنني فعله:\n"
    "💬 اسألني أي سؤال، أو اكتب مشكلتك وسأرشح لك تطبيقات من القناة.\n"
    "🕌 /city اختيار الدولة والمدينة\n"
    "⏰ /remind تشغيل/إيقاف تذكير الصلاة\n"
    "📿 /prayers مواقيت اليوم\n"
    "🆕 /latest أحدث منشورات القناة\n"
    "✏️ /name تغيير الاسم الذي أناديك به\n"
    "🗑 /forget حذف بياناتي\n"
    "ℹ️ /about عن المشروع"
)


# ---------------------------------------------------------------- الأوامر
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db = _db(ctx)
    row = db.ensure_user(u.id, u.first_name or "")
    ctx.user_data.pop("state", None)
    if not _name(row):
        ctx.user_data["state"] = "await_name"
        await update.message.reply_text(WELCOME_NEW.format(bot=_s(ctx).bot_name))
        return
    extra = "" if row["lat"] is not None else "\n\nلتفعيل تذكير الصلاة أرسل /city."
    await update.message.reply_text(f"أهلًا بك من جديد يا {_name(row)} 🌿\n\n{HELP}{extra}")


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)


async def about_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = _s(ctx)
    c = _db(ctx).doc_count()
    await update.message.reply_text(
        f"{s.bot_name}\n"
        "مشروع مفتوح المصدر ومجاني بالكامل، صدقة جارية نسأل الله قبولها 🤍\n"
        f"📚 أعرف حاليًا: {c.get('channel', 0)} مقطعًا من القناة و{c.get('group', 0)} من المجموعة.\n"
        "⚠️ أنا ذكاء اصطناعي ولست مفتيًا؛ في المسائل الدقيقة اسأل أهل العلم.\n"
        + (f"\n{s.project_url}" if s.project_url else ""),
        disable_web_page_preview=True,
    )


async def skip_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("state", None)
    await update.message.reply_text("تمام ✅ يمكنك تغيير الاسم لاحقًا بأمر /name. اسألني ما تشاء!")


async def name_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        await _save_name(update, ctx, " ".join(ctx.args))
        return
    ctx.user_data["state"] = "await_name"
    await update.message.reply_text("اكتب الاسم الذي تحب أن أناديك به 🌿")


async def _save_name(update: Update, ctx, raw: str):
    name = guard.clean_name(raw)
    if not name:
        await update.effective_message.reply_text(
            "لم أستطع استخدام هذا الاسم. اكتب اسمًا بسيطًا (حروف فقط، حتى 3 كلمات)."
        )
        return
    _db(ctx).set_user(update.effective_user.id, preferred_name=name)
    ctx.user_data.pop("state", None)
    row = _db(ctx).get_user(update.effective_user.id)
    msg = f"تشرفت بك يا {name} 🌿"
    if row["lat"] is None:
        msg += "\nلتفعيل تذكير الصلاة اختر دولتك ومدينتك بأمر /city."
    await update.effective_message.reply_text(msg)


# ---- المدينة والمواقيت
def _countries_keyboard() -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(c[1], callback_data=f"c:{c[0]}") for c in COUNTRIES]
    rows = [btns[i : i + 3] for i in range(0, len(btns), 3)]
    rows.append([InlineKeyboardButton("🌍 دولة أخرى", callback_data="c:OTHER")])
    return InlineKeyboardMarkup(rows)


async def city_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("state", None)
    await update.message.reply_text("اختر دولتك:", reply_markup=_countries_keyboard())


_CITY_OK = re.compile(r"^[\w\s\u0600-\u06FF'\-\.,]{2,60}$")


async def _handle_location_text(update: Update, ctx, text: str) -> None:
    st = ctx.user_data.get("state")
    uid = update.effective_user.id
    if st == "await_country":
        c = find_country(text)
        if c:
            ctx.user_data.update(state="await_city", country=c[0], country_text=None)
        elif _CITY_OK.match(text):
            ctx.user_data.update(state="await_city", country=None, country_text=text)
        else:
            await update.message.reply_text("اكتب اسم الدولة بالعربية أو الإنجليزية.")
            return
        await update.message.reply_text("جميل. الآن اكتب اسم مدينتك (بالعربية أو الإنجليزية):")
        return

    # await_city
    if not _CITY_OK.match(text):
        await update.message.reply_text("اكتب اسم المدينة فقط (حروف وأرقام بسيطة).")
        return
    code = ctx.user_data.get("country")
    ctext = ctx.user_data.get("country_text")
    prayer = ctx.bot_data["prayer"]
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    geo = await prayer.geocode(text, code, ctext)
    if not geo:
        await update.message.reply_text(
            "لم أجد هذه المدينة 🤔 جرّب كتابتها بالإنجليزية، أو أضف اسم المحافظة (مثال: Ismailia)."
        )
        return
    cc = geo["country_code"] or code or ""
    country = by_code(cc)
    method = country[3] if country else DEFAULT_METHOD
    country_name = country[1] if country else (geo["country_name"] or ctext or "")
    try:
        tz = await prayer.resolve_tz(geo["lat"], geo["lon"], method)
    except Exception:  # noqa: BLE001
        log.exception("resolve_tz failed")
        await update.message.reply_text("تعذّر الوصول لخدمة المواقيت الآن. جرّب بعد قليل من فضلك.")
        return
    _db(ctx).set_user(
        uid, country_code=cc, country_name=country_name, city=text.strip(),
        lat=geo["lat"], lon=geo["lon"], tz=tz, method=method, reminders_on=1,
    )
    ctx.user_data.pop("state", None)
    await update.message.reply_text(
        f"✅ تم: {text.strip()}، {country_name}\n"
        "فعّلت تذكير الصلاة تلقائيًا (يمكنك تغييره من /remind). اكتب /prayers لتشاهد مواقيت اليوم."
    )


def _times_text(u, day) -> str:
    t = day["timings"]
    lines = [f"🕌 مواقيت الصلاة — {u['city']}، {u['country_name']}"]
    if day.get("hijri"):
        lines.append(f"📅 {day['hijri']} هـ")
    lines.append("")
    for key, ar in PRAYERS[:1]:
        lines.append(f"{ar}: {t[key]}")
    if "Sunrise" in t:
        lines.append(f"الشروق: {t['Sunrise']}")
    for key, ar in PRAYERS[1:]:
        lines.append(f"{ar}: {t[key]}")
    return "\n".join(lines)


async def prayers_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = _db(ctx).get_user(update.effective_user.id)
    if not u or u["lat"] is None:
        await update.message.reply_text("لم تحدد مدينتك بعد. أرسل /city أولًا 🕌")
        return
    now = datetime.now(ZoneInfo(u["tz"]))
    try:
        day = await ctx.bot_data["prayer"].get_day(u["lat"], u["lon"], u["method"], now.date())
    except Exception:  # noqa: BLE001
        log.exception("get_day failed")
        await update.message.reply_text("تعذّر جلب المواقيت الآن، جرّب بعد قليل.")
        return
    await update.message.reply_text(_times_text(u, day))


def _remind_view(u) -> tuple[str, InlineKeyboardMarkup]:
    on = bool(u["reminders_on"])
    lead = u["lead_min"] or 0
    text = (
        f"⏰ تذكير الصلاة: {'مفعّل ✅' if on else 'متوقف ⛔'}\n"
        f"📍 {u['city']}، {u['country_name']}\n"
        f"التنبيه: {'عند الأذان' if lead == 0 else f'قبل الأذان بـ {lead} دقيقة'}"
    )
    mark = lambda n: ("✔️ " if lead == n else "")  # noqa: E731
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("إيقاف التذكير" if on else "تشغيل التذكير", callback_data="r:toggle")],
            [
                InlineKeyboardButton(f"{mark(0)}عند الأذان", callback_data="r:lead:0"),
                InlineKeyboardButton(f"{mark(5)}قبل 5", callback_data="r:lead:5"),
                InlineKeyboardButton(f"{mark(10)}قبل 10", callback_data="r:lead:10"),
                InlineKeyboardButton(f"{mark(15)}قبل 15", callback_data="r:lead:15"),
            ],
        ]
    )
    return text, kb


async def remind_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = _db(ctx).get_user(update.effective_user.id)
    if not u or u["lat"] is None:
        await update.message.reply_text("لتفعيل التذكير اختر مدينتك أولًا بأمر /city 🕌")
        return
    text, kb = _remind_view(u)
    await update.message.reply_text(text, reply_markup=kb)


async def latest_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = _db(ctx).latest_posts(8)
    if not rows:
        await update.message.reply_text("لم أحمّل منشورات القناة بعد. جرّب بعد دقائق.")
        return
    lines = ["🆕 أحدث منشورات القناة:\n"] + [f"• {r['title'][:70]}\n{r['url']}" for r in rows]
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def forget_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("نعم، احذف", callback_data="f:yes"), InlineKeyboardButton("إلغاء", callback_data="f:no")]]
    )
    await update.message.reply_text("سأحذف اسمك ومدينتك ومحادثاتك المخزّنة نهائيًا. متأكد؟", reply_markup=kb)


# ---- أوامر المشرفين
def _is_bot_admin(update: Update, ctx) -> bool:
    return update.effective_user.id in _s(ctx).admin_ids


async def sync_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_bot_admin(update, ctx):
        return
    full = bool(ctx.args and ctx.args[0] == "full")
    await update.message.reply_text("جارٍ المزامنة…")
    res = await knowledge.sync_channel(_db(ctx), _s(ctx).channel, full=full)
    await update.message.reply_text(f"تمت المزامنة: {res}")


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_bot_admin(update, ctx):
        return
    await update.message.reply_text(str(_db(ctx).stats()))


# ---------------------------------------------------------------- الأزرار
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    uid = q.from_user.id
    db = _db(ctx)
    await q.answer()

    if data.startswith("c:"):
        code = data[2:]
        if code == "OTHER":
            ctx.user_data["state"] = "await_country"
            await q.edit_message_text("اكتب اسم دولتك:")
            return
        c = by_code(code)
        if not c:
            return
        ctx.user_data.update(state="await_city", country=c[0], country_text=None)
        await q.edit_message_text(f"الدولة: {c[1]} ✅\nالآن اكتب اسم مدينتك (بالعربية أو الإنجليزية):")
        return

    if data.startswith("r:"):
        u = db.get_user(uid)
        if not u or u["lat"] is None:
            return
        if data == "r:toggle":
            db.set_user(uid, reminders_on=0 if u["reminders_on"] else 1)
        elif data.startswith("r:lead:"):
            try:
                lead = int(data.split(":")[2])
            except ValueError:
                return
            if lead in (0, 5, 10, 15):
                db.set_user(uid, lead_min=lead)
        text, kb = _remind_view(db.get_user(uid))
        try:
            await q.edit_message_text(text, reply_markup=kb)
        except TelegramError:
            pass
        return

    if data == "f:yes":
        db.delete_user(uid)
        ctx.user_data.clear()
        await q.edit_message_text("تم حذف بياناتك 🗑 يمكنك البدء من جديد بـ /start.")
    elif data == "f:no":
        await q.edit_message_text("تم الإلغاء ✅")


# ---------------------------------------------------------------- الرسائل
async def on_private_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    text = (msg.text or "").strip()
    if not text:
        return
    s, db = _s(ctx), _db(ctx)
    db.ensure_user(user.id, user.first_name or "")

    state = ctx.user_data.get("state")
    if state == "await_name":
        await _save_name(update, ctx, text)
        return
    if state in ("await_country", "await_city"):
        await _handle_location_text(update, ctx, text)
        return

    # اسم بلغة طبيعية: «نادني أحمد»
    nm = extract_name(text)
    if nm:
        await _save_name(update, ctx, nm)
        return

    if rate_limited(user.id, s.per_minute):
        await msg.reply_text("⏳ مهلًا قليلًا، رسائلك كثيرة في وقت قصير. جرّب بعد دقيقة.")
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if db.bump_usage(user.id, today) > s.daily_limit:
        await msg.reply_text("وصلت للحد اليومي للرسائل (للحفاظ على الخدمة مجانية للجميع). نلتقي غدًا بإذن الله 🤍")
        return

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    row = db.get_user(user.id)
    reply = await ctx.bot_data["assistant"].reply(user.id, _name(row), text[:1500])
    await send_long(update, reply.text)


async def _is_group_admin(ctx, chat, msg) -> bool:
    if msg.sender_chat and msg.sender_chat.id == chat.id:
        return True  # مشرف مجهول
    if msg.from_user and msg.from_user.id == 1087968824:  # GroupAnonymousBot
        return True
    cache = ctx.bot_data.setdefault("admin_cache", {})
    exp, ids = cache.get(chat.id, (0, set()))
    if time.time() > exp:
        try:
            ids = {a.user.id for a in await ctx.bot.get_chat_administrators(chat.id)}
        except TelegramError:
            ids = set()
        cache[chat.id] = (time.time() + 600, ids)
    return bool(msg.from_user and msg.from_user.id in ids)


async def on_group_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يتعلم من المجموعة المحددة فقط (LEARN_GROUPS)، ولا يردّ فيها."""
    msg, chat = update.effective_message, update.effective_chat
    s, db = _s(ctx), _db(ctx)
    uname = (chat.username or "").lower()
    if not msg or uname not in s.learn_groups:
        return
    text = (msg.text or "").strip()
    if len(text) < 12 or text.startswith("/") or not guard.is_safe_to_ingest(text):
        return
    db.add_group_msg(uname, msg.message_id, text)  # مخزن مؤقت للأسئلة (14 يومًا، بلا هوية)
    is_admin = await _is_group_admin(ctx, chat, msg)
    if s.group_learn_mode == "admins" and not is_admin:
        return
    question = None
    rt = msg.reply_to_message
    if rt:
        question = db.get_group_msg(uname, rt.message_id) or (rt.text or None)
        if question and not guard.is_safe_to_ingest(question):
            return
    if not question and len(text) < 40:
        return
    db.upsert_doc(**knowledge.group_doc(uname, msg.message_id, text, question, is_admin))


# ---------------------------------------------------------------- المهام الدورية
async def reminder_tick(ctx: ContextTypes.DEFAULT_TYPE):
    db, prayer = _db(ctx), ctx.bot_data["prayer"]
    for u in db.reminder_users():
        try:
            now = datetime.now(ZoneInfo(u["tz"]))
            day = await prayer.get_day(u["lat"], u["lon"], u["method"], now.date())
            for key in due_prayers(day["timings"], now, u["lead_min"] or 0):
                d = now.date().isoformat()
                if db.was_sent(u["user_id"], d, key):
                    continue
                db.mark_sent(u["user_id"], d, key)
                h, m = hm(day["timings"][key])
                text = reminder_text(_name(u), key, f"{h:02d}:{m:02d}", u["city"], u["lead_min"] or 0)
                try:
                    await ctx.bot.send_message(u["user_id"], text)
                except Forbidden:
                    db.set_user(u["user_id"], reminders_on=0)  # المستخدم حظر البوت
                except TelegramError as e:
                    log.warning("reminder send failed for %s: %s", u["user_id"], e)
        except Exception:  # noqa: BLE001
            log.exception("reminder_tick failed for user %s", u["user_id"])


async def sync_job(ctx: ContextTypes.DEFAULT_TYPE):
    try:
        await knowledge.sync_channel(_db(ctx), _s(ctx).channel)
        _db(ctx).prune_group_msgs()
    except Exception:  # noqa: BLE001
        log.exception("sync_job failed")
