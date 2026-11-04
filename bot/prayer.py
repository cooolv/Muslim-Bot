"""مواقيت الصلاة (Aladhan API) + تحديد المدينة (OpenStreetMap Nominatim) + منطق التذكير.

كلاهما مجاني ولا يحتاج مفتاحًا.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .db import DB

log = logging.getLogger(__name__)

PRAYERS = [
    ("Fajr", "الفجر"),
    ("Dhuhr", "الظهر"),
    ("Asr", "العصر"),
    ("Maghrib", "المغرب"),
    ("Isha", "العشاء"),
]
AR_NAME = dict(PRAYERS)
_HM = re.compile(r"(\d{1,2}):(\d{2})")


def hm(value: str) -> tuple[int, int]:
    m = _HM.search(value)
    if not m:
        raise ValueError(f"وقت غير صالح: {value!r}")
    return int(m.group(1)), int(m.group(2))


def due_prayers(timings: dict[str, str], now: datetime, lead_min: int = 0, window_s: int = 120) -> list[str]:
    """الصلوات التي حان وقت تذكيرها الآن (داخل نافذة window_s ثانية)."""
    due = []
    for key, _ in PRAYERS:
        if key not in timings:
            continue
        h, m = hm(timings[key])
        target = now.replace(hour=h, minute=m, second=0, microsecond=0) - timedelta(minutes=lead_min)
        if 0 <= (now - target).total_seconds() < window_s:
            due.append(key)
    return due


class PrayerService:
    def __init__(self, db: DB, user_agent: str):
        self.db = db
        self.ua = {"User-Agent": user_agent}
        self._mem: dict[str, dict[str, Any]] = {}
        self._client = None
        self._geo_lock = asyncio.Lock()

    async def client(self):
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20, follow_redirects=True)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    # ---------- تحديد المدينة ----------
    async def geocode(self, city: str, country_code: str | None = None, country_text: str | None = None) -> dict | None:
        q = f"{city}, {country_text}" if country_text and not country_code else city
        params = {"q": q, "format": "jsonv2", "limit": 1, "accept-language": "ar", "addressdetails": 1}
        if country_code:
            params["countrycodes"] = country_code.lower()
        async with self._geo_lock:  # سياسة Nominatim: طلب واحد/ثانية
            try:
                r = await (await self.client()).get(
                    "https://nominatim.openstreetmap.org/search", params=params, headers=self.ua
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("geocode failed: %s", e)
                return None
            finally:
                await asyncio.sleep(1.0)
        if not data:
            return None
        it = data[0]
        addr = it.get("address", {})
        return {
            "lat": float(it["lat"]),
            "lon": float(it["lon"]),
            "name": it.get("name") or city,
            "country_code": (addr.get("country_code") or country_code or "").upper(),
            "country_name": addr.get("country") or country_text or "",
        }

    # ---------- المواقيت ----------
    async def get_day(self, lat: float, lon: float, method: int, d: date, tz_hint: str | None = None) -> dict[str, Any]:
        key = f"{lat:.2f},{lon:.2f},{method},{d.isoformat()}"
        if key in self._mem:
            return self._mem[key]
        cached = self.db.cache_get(key)
        if cached:
            self._mem[key] = json.loads(cached)
            return self._mem[key]

        url = f"https://api.aladhan.com/v1/timings/{d.strftime('%d-%m-%Y')}"
        r = await (await self.client()).get(
            url, params={"latitude": lat, "longitude": lon, "method": method}, headers=self.ua
        )
        r.raise_for_status()
        data = r.json()["data"]
        h = data.get("date", {}).get("hijri", {})
        result = {
            "timings": {k: v.split(" ")[0] for k, v in data["timings"].items() if k in AR_NAME or k == "Sunrise"},
            "tz": data["meta"]["timezone"],
            "hijri": f"{h.get('day', '')} {h.get('month', {}).get('ar', '')} {h.get('year', '')}".strip(),
        }
        self.db.cache_set(key, json.dumps(result, ensure_ascii=False))
        if len(self._mem) > 2000:
            self._mem.clear()
        self._mem[key] = result
        return result

    async def resolve_tz(self, lat: float, lon: float, method: int) -> str:
        """يعرف المنطقة الزمنية من أول استدعاء (تاريخ UTC اليوم)، ثم يُخزَّن في المستخدم."""
        day = await self.get_day(lat, lon, method, datetime.now(timezone.utc).date())
        return day["tz"]


def reminder_text(name: str, prayer_key: str, hhmm: str, city: str, lead_min: int) -> str:
    ar = AR_NAME[prayer_key]
    who = f"{name}، " if name else ""
    if lead_min > 0:
        return f"🕌 {who}باقي {lead_min} دقيقة على أذان {ar} ({hhmm}) بتوقيت {city}."
    text = f"🕌 {who}حان الآن موعد أذان {ar} ({hhmm}) بتوقيت {city}.\n"
    text += "الصلاة خير من النوم 🌙\n" if prayer_key == "Fajr" else ""
    text += "قم إلى الصلاة، جعلنا الله وإياك من المحافظين عليها 🤍"
    return text
