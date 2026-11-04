"""نقطة التشغيل:  python -m bot.main"""
from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters,
)

from . import handlers as h
from .assistant import Assistant
from .config import get_settings
from .db import DB
from .llm import LLM
from .prayer import PrayerService

COMMANDS = [
    ("start", "بدء الاستخدام"),
    ("city", "اختيار الدولة والمدينة"),
    ("prayers", "مواقيت اليوم"),
    ("remind", "إعدادات تذكير الصلاة"),
    ("latest", "أحدث منشورات القناة"),
    ("name", "الاسم الذي أناديك به"),
    ("forget", "حذف بياناتي"),
    ("about", "عن المشروع"),
    ("help", "المساعدة"),
]


def build_app() -> Application:
    s = get_settings()
    db = DB(s.db_path)
    llm = LLM(s.providers, s.guard_models)
    ua = f"MuslimAppsBot/1.0 ({s.project_url or 'open-source'})"
    prayer = PrayerService(db, ua)

    async def post_init(app: Application):
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])

    async def post_shutdown(app: Application):
        await llm.close()
        await prayer.close()

    app = Application.builder().token(s.telegram_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.bot_data.update(settings=s, db=db, prayer=prayer, assistant=Assistant(db, llm, s))

    for name, fn in [
        ("start", h.start), ("help", h.help_cmd), ("about", h.about_cmd), ("skip", h.skip_cmd),
        ("name", h.name_cmd), ("city", h.city_cmd), ("prayers", h.prayers_cmd), ("remind", h.remind_cmd),
        ("latest", h.latest_cmd), ("forget", h.forget_cmd), ("sync", h.sync_cmd), ("stats", h.stats_cmd),
    ]:
        app.add_handler(CommandHandler(name, fn, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(h.on_callback))
    plain = filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE
    app.add_handler(MessageHandler(plain & filters.ChatType.PRIVATE, h.on_private_text))
    app.add_handler(MessageHandler(plain & filters.ChatType.GROUPS, h.on_group_text))

    async def on_error(update, context):
        logging.getLogger("bot").exception("Unhandled error", exc_info=context.error)

    app.add_error_handler(on_error)

    if app.job_queue is None:
        raise SystemExit('ثبّت المتطلبات كاملة: pip install "python-telegram-bot[job-queue]"')
    app.job_queue.run_repeating(h.reminder_tick, interval=30, first=20, name="prayer-reminders")
    app.job_queue.run_repeating(h.sync_job, interval=s.sync_hours * 3600, first=5, name="channel-sync")
    return app


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_app().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
