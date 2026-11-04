"""الإعدادات: كلها من متغيرات البيئة (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _list(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    providers: tuple[Provider, ...]
    guard_models: tuple[str, ...]
    use_llm_guard: bool
    channel: str
    learn_groups: tuple[str, ...]
    group_learn_mode: str  # "admins" | "all"
    sync_hours: int
    daily_limit: int
    per_minute: int
    admin_ids: frozenset[int]
    bot_name: str
    project_url: str
    db_path: str
    history_turns: int = 3


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    if not token or not key:
        raise SystemExit(
            "❌ لازم تحدد TELEGRAM_BOT_TOKEN و LLM_API_KEY في ملف .env (شوف .env.example)"
        )

    providers = [
        Provider(
            "primary",
            os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            key,
            _list("LLM_MODELS", "llama-3.3-70b-versatile,llama-3.1-8b-instant"),
        )
    ]
    fb_key = os.getenv("FALLBACK_LLM_API_KEY", "").strip()
    if fb_key:
        providers.append(
            Provider(
                "fallback",
                os.getenv("FALLBACK_LLM_BASE_URL", "").rstrip("/"),
                fb_key,
                _list("FALLBACK_LLM_MODELS"),
            )
        )

    admin_ids = frozenset(int(x) for x in _list("ADMIN_IDS") if x.lstrip("-").isdigit())
    mode = os.getenv("GROUP_LEARN_MODE", "admins").strip().lower()
    return Settings(
        telegram_token=token,
        providers=tuple(p for p in providers if p.base_url and p.models),
        guard_models=_list("LLM_GUARD_MODELS", "llama-3.1-8b-instant"),
        use_llm_guard=_bool("USE_LLM_GUARD", True),
        channel=os.getenv("CHANNEL_USERNAME", "muslim_appss").strip().lstrip("@"),
        learn_groups=tuple(g.lower().lstrip("@") for g in _list("LEARN_GROUPS", "muslimappss")),
        group_learn_mode="all" if mode == "all" else "admins",
        sync_hours=max(1, _int("SYNC_HOURS", 6)),
        daily_limit=max(1, _int("DAILY_LIMIT_PER_USER", 40)),
        per_minute=max(1, _int("PER_MINUTE_LIMIT", 8)),
        admin_ids=admin_ids,
        bot_name=os.getenv("BOT_NAME", "مساعد تطبيقات المسلم").strip(),
        project_url=os.getenv("PROJECT_URL", "").strip(),
        db_path=os.getenv("DB_PATH", "data/bot.db").strip(),
    )
