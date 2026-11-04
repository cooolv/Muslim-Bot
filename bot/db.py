"""طبقة قاعدة البيانات (SQLite + FTS5) — ملف واحد بلا خدمات خارجية."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Iterable

from .arabic import fts_query, index_text

USER_FIELDS = {
    "first_name", "preferred_name", "country_code", "country_name", "city",
    "lat", "lon", "tz", "method", "reminders_on", "lead_min",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    first_name     TEXT,
    preferred_name TEXT,
    country_code   TEXT,
    country_name   TEXT,
    city           TEXT,
    lat            REAL,
    lon            REAL,
    tz             TEXT,
    method         INTEGER DEFAULT 3,
    reminders_on   INTEGER DEFAULT 0,
    lead_min       INTEGER DEFAULT 0,
    created_at     INTEGER
);
CREATE TABLE IF NOT EXISTS docs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT NOT NULL,           -- channel | group
    ref       TEXT NOT NULL UNIQUE,    -- channel:656#0 | group:muslimappss:123
    post_id   INTEGER,
    chunk_idx INTEGER DEFAULT 0,
    title     TEXT,
    body      TEXT NOT NULL,
    url       TEXT,
    trust     INTEGER DEFAULT 1,       -- 3 قناة | 2 مشرف | 1 عضو
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_docs_post ON docs(source, post_id);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(norm, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id);
CREATE TABLE IF NOT EXISTS sent_reminders (
    user_id INTEGER, day TEXT, prayer TEXT,
    PRIMARY KEY (user_id, day, prayer)
);
CREATE TABLE IF NOT EXISTS prayer_cache (key TEXT PRIMARY KEY, json TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS group_msgs (
    chat TEXT, msg_id INTEGER, text TEXT, ts INTEGER,
    PRIMARY KEY (chat, msg_id)
);
CREATE TABLE IF NOT EXISTS usage (user_id INTEGER, day TEXT, n INTEGER DEFAULT 0, PRIMARY KEY (user_id, day));
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


class DB:
    def __init__(self, path: str):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ---------- أدوات ----------
    def q(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchall()

    def one(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchone()

    def x(self, sql: str, args: Iterable[Any] = ()) -> None:
        with self.lock:
            self.conn.execute(sql, tuple(args))
            self.conn.commit()

    # ---------- المستخدمون ----------
    def get_user(self, uid: int) -> sqlite3.Row | None:
        return self.one("SELECT * FROM users WHERE user_id=?", (uid,))

    def ensure_user(self, uid: int, first_name: str = "") -> sqlite3.Row:
        if not self.get_user(uid):
            self.x(
                "INSERT INTO users(user_id, first_name, created_at) VALUES (?,?,?)",
                (uid, first_name, int(time.time())),
            )
        return self.get_user(uid)  # type: ignore[return-value]

    def set_user(self, uid: int, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if k in USER_FIELDS}
        if not fields:
            return
        self.ensure_user(uid)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE users SET {cols} WHERE user_id=?", (*fields.values(), uid))

    def delete_user(self, uid: int) -> None:
        with self.lock:
            for t in ("users", "history", "sent_reminders", "usage"):
                self.conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
            self.conn.commit()

    def reminder_users(self) -> list[sqlite3.Row]:
        return self.q(
            "SELECT * FROM users WHERE reminders_on=1 AND lat IS NOT NULL AND tz IS NOT NULL"
        )

    # ---------- المعرفة ----------
    def upsert_doc(
        self, *, ref: str, source: str, body: str, title: str = "", url: str = "",
        post_id: int | None = None, chunk_idx: int = 0, trust: int = 1,
    ) -> None:
        norm = index_text(f"{title} {body}")
        with self.lock:
            row = self.conn.execute("SELECT id FROM docs WHERE ref=?", (ref,)).fetchone()
            if row:
                did = row["id"]
                self.conn.execute(
                    "UPDATE docs SET body=?, title=?, url=?, post_id=?, chunk_idx=?, trust=? WHERE id=?",
                    (body, title, url, post_id, chunk_idx, trust, did),
                )
                self.conn.execute("DELETE FROM docs_fts WHERE rowid=?", (did,))
            else:
                cur = self.conn.execute(
                    "INSERT INTO docs(source, ref, post_id, chunk_idx, title, body, url, trust, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (source, ref, post_id, chunk_idx, title, body, url, trust, int(time.time())),
                )
                did = cur.lastrowid
            self.conn.execute("INSERT INTO docs_fts(rowid, norm) VALUES (?,?)", (did, norm))
            self.conn.commit()

    def delete_post_chunks(self, source: str, post_id: int) -> None:
        with self.lock:
            ids = [r["id"] for r in self.conn.execute(
                "SELECT id FROM docs WHERE source=? AND post_id=?", (source, post_id))]
            for i in ids:
                self.conn.execute("DELETE FROM docs_fts WHERE rowid=?", (i,))
            self.conn.execute("DELETE FROM docs WHERE source=? AND post_id=?", (source, post_id))
            self.conn.commit()

    def search(self, tokens: list[str], k: int = 5, max_per_post: int = 2) -> list[sqlite3.Row]:
        match = fts_query(tokens)
        if not match:
            return []
        try:
            rows = self.q(
                "SELECT d.*, bm25(docs_fts) AS score FROM docs_fts "
                "JOIN docs d ON d.id = docs_fts.rowid "
                "WHERE docs_fts MATCH ? ORDER BY score LIMIT ?",
                (match, k * 6),
            )
        except sqlite3.OperationalError:
            return []
        # bm25: الأقل (الأكثر سلبية) هو الأفضل؛ نُضخّم قيمة الموثوق أكثر
        ranked = sorted(rows, key=lambda r: r["score"] * (1 + 0.25 * ((r["trust"] or 1) - 1)))
        out, per_post = [], {}
        for r in ranked:
            key = (r["source"], r["post_id"] if r["post_id"] is not None else r["id"])
            if per_post.get(key, 0) >= max_per_post:
                continue
            per_post[key] = per_post.get(key, 0) + 1
            out.append(r)
            if len(out) >= k:
                break
        return out

    def latest_posts(self, n: int = 8) -> list[sqlite3.Row]:
        return self.q(
            "SELECT * FROM docs WHERE source='channel' AND chunk_idx=0 "
            "ORDER BY post_id DESC LIMIT ?", (n,))

    def doc_count(self) -> dict[str, int]:
        return {r["source"]: r["n"] for r in self.q("SELECT source, COUNT(*) n FROM docs GROUP BY source")}

    # ---------- رسائل المجموعة (مخزن مؤقت للأسئلة) ----------
    def add_group_msg(self, chat: str, msg_id: int, text: str) -> None:
        self.x("INSERT OR REPLACE INTO group_msgs VALUES (?,?,?,?)", (chat, msg_id, text, int(time.time())))

    def get_group_msg(self, chat: str, msg_id: int) -> str | None:
        r = self.one("SELECT text FROM group_msgs WHERE chat=? AND msg_id=?", (chat, msg_id))
        return r["text"] if r else None

    def prune_group_msgs(self, days: int = 14) -> None:
        self.x("DELETE FROM group_msgs WHERE ts < ?", (int(time.time()) - days * 86400,))

    # ---------- المحادثة ----------
    def add_history(self, uid: int, role: str, content: str, keep: int = 12) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO history(user_id, role, content, ts) VALUES (?,?,?,?)",
                (uid, role, content[:2000], int(time.time())),
            )
            self.conn.execute(
                "DELETE FROM history WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?)",
                (uid, uid, keep),
            )
            self.conn.commit()

    def get_history(self, uid: int, n: int = 6) -> list[dict[str, str]]:
        rows = self.q("SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, n))
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_history(self, uid: int) -> None:
        self.x("DELETE FROM history WHERE user_id=?", (uid,))

    # ---------- الحدود ----------
    def bump_usage(self, uid: int, day: str) -> int:
        with self.lock:
            self.conn.execute(
                "INSERT INTO usage(user_id, day, n) VALUES (?,?,1) "
                "ON CONFLICT(user_id, day) DO UPDATE SET n = n + 1", (uid, day))
            self.conn.execute("DELETE FROM usage WHERE day < date(?, '-3 day')", (day,))
            self.conn.commit()
            return self.conn.execute("SELECT n FROM usage WHERE user_id=? AND day=?", (uid, day)).fetchone()["n"]

    # ---------- التذكيرات ----------
    def was_sent(self, uid: int, day: str, prayer: str) -> bool:
        return self.one("SELECT 1 FROM sent_reminders WHERE user_id=? AND day=? AND prayer=?", (uid, day, prayer)) is not None

    def mark_sent(self, uid: int, day: str, prayer: str) -> None:
        self.x("INSERT OR IGNORE INTO sent_reminders VALUES (?,?,?)", (uid, day, prayer))
        self.x("DELETE FROM sent_reminders WHERE day < date(?, '-3 day')", (day,))

    def cache_get(self, key: str) -> str | None:
        r = self.one("SELECT json FROM prayer_cache WHERE key=?", (key,))
        return r["json"] if r else None

    def cache_set(self, key: str, value: str) -> None:
        self.x("INSERT OR REPLACE INTO prayer_cache VALUES (?,?,?)", (key, value, int(time.time())))
        self.x("DELETE FROM prayer_cache WHERE ts < ?", (int(time.time()) - 5 * 86400,))

    # ---------- مفتاح/قيمة ----------
    def get_kv(self, k: str) -> str | None:
        r = self.one("SELECT v FROM kv WHERE k=?", (k,))
        return r["v"] if r else None

    def set_kv(self, k: str, v: str) -> None:
        self.x("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, v))

    def stats(self) -> dict[str, Any]:
        return {
            "users": self.one("SELECT COUNT(*) n FROM users")["n"],
            "with_reminders": self.one("SELECT COUNT(*) n FROM users WHERE reminders_on=1")["n"],
            "docs": self.doc_count(),
        }
