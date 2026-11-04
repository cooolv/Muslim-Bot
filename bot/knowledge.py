"""جلب منشورات القناة العامة (t.me/s/...) وفهرستها، وتعلّم المجموعة."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .db import DB

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; MuslimAppsBot/1.0; +open-source)"}
_HASHTAG_LINK = re.compile(r"[?&]q=%23")


@dataclass
class Post:
    id: int
    text: str
    url: str
    date: str = ""


def parse_posts(html: str, channel: str) -> list[Post]:
    """يحلل صفحة t.me/s/<channel> ويعيد المنشورات (حتى التي بلا نص، لنعرف أرقامها)."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        try:
            pid = int(msg["data-post"].rsplit("/", 1)[1])
        except (ValueError, IndexError, KeyError):
            continue
        parts: list[str] = []

        doc_title = msg.select_one(".tgme_widget_message_document_title")
        if doc_title:
            parts.append("ملف: " + doc_title.get_text(" ", strip=True))

        text_el = msg.select_one("div.js-message_text") or msg.select_one("div.tgme_widget_message_text")
        links: list[str] = []
        if text_el:
            for br in text_el.find_all("br"):
                br.replace_with("\n")
            for a in text_el.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http") and not _HASHTAG_LINK.search(href):
                    if href not in links:
                        links.append(href)
            txt = text_el.get_text("")
            txt = re.sub(r"[ \t]+\n", "\n", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
            if txt:
                parts.append(txt)

        for sel in (".link_preview_title", ".link_preview_description"):
            el = msg.select_one(sel)
            if el and el.get_text(strip=True):
                parts.append(el.get_text(" ", strip=True))

        if links:
            parts.append("روابط: " + " ".join(links[:6]))

        t = msg.select_one("time[datetime]")
        posts.append(
            Post(
                id=pid,
                text="\n".join(parts).strip(),
                url=f"https://t.me/{channel}/{pid}",
                date=t["datetime"] if t else "",
            )
        )
    return posts


def chunk_text(text: str, size: int = 900) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for p in (p.strip() for p in text.split("\n")):
        if not p:
            continue
        if len(cur) + len(p) + 1 <= size:
            cur = f"{cur}\n{p}".strip()
        else:
            if cur:
                chunks.append(cur)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def _title_of(text: str) -> str:
    first = next((l.strip() for l in text.split("\n") if l.strip()), "")
    return first[:90]


def index_post(db: DB, post: Post) -> bool:
    """يفهرس منشورًا (يستبدل نسخته القديمة). يعيد True إن كان فيه نص."""
    db.delete_post_chunks("channel", post.id)
    if not post.text:
        return False
    title = _title_of(post.text)
    for i, ch in enumerate(chunk_text(post.text)):
        db.upsert_doc(
            ref=f"channel:{post.id}#{i}", source="channel", body=ch, title=title,
            url=post.url, post_id=post.id, chunk_idx=i, trust=3,
        )
    return True


async def fetch_page(client, channel: str, before: int | None = None) -> list[Post]:
    params = {"before": before} if before else None
    r = await client.get(f"https://t.me/s/{channel}", params=params, headers=UA)
    r.raise_for_status()
    return parse_posts(r.text, channel)


async def sync_channel(db: DB, channel: str, full: bool = False, max_pages: int = 120) -> dict[str, int]:
    """مزامنة القناة. أول مرة تكون كاملة، وبعدها تحديث للجديد + آخر ~30 منشورًا (لالتقاط التعديلات)."""
    import httpx

    last = int(db.get_kv(f"{channel}:max_id") or 0)
    full = full or last == 0
    before: int | None = None
    pages = indexed = 0
    max_id = last
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        while pages < max_pages:
            try:
                posts = await fetch_page(client, channel, before)
            except Exception as e:  # noqa: BLE001
                log.warning("sync: فشل جلب الصفحة (before=%s): %s", before, e)
                break
            if not posts:
                break
            pages += 1
            for p in posts:
                indexed += index_post(db, p)
                max_id = max(max_id, p.id)
            min_id = min(p.id for p in posts)
            if min_id <= 1 or (not full and min_id < last - 30):
                break
            before = min_id
            await asyncio.sleep(1.0)
    if max_id:
        db.set_kv(f"{channel}:max_id", str(max_id))
    log.info("sync: pages=%s indexed=%s max_id=%s", pages, indexed, max_id)
    return {"pages": pages, "indexed": indexed, "max_id": max_id}


# ---------- المجموعة ----------
def group_doc(chat_username: str, msg_id: int, text: str, question: str | None, is_admin: bool) -> dict:
    """يبني وثيقة معرفة من رسالة في المجموعة (سؤال/جواب إن توفّر)."""
    body = f"سؤال: {question.strip()}\nجواب: {text.strip()}" if question else text.strip()
    return dict(
        ref=f"group:{chat_username}:{msg_id}",
        source="group",
        body=body[:1500],
        title=(question or text)[:90],
        url=f"https://t.me/{chat_username}/{msg_id}",
        trust=2 if is_admin else 1,
    )
