from bot.arabic import query_tokens
from bot.db import DB
from bot.knowledge import chunk_text, group_doc, index_post, parse_posts

HTML = """
<div class="tgme_widget_message" data-post="muslim_appss/640">
 <div class="tgme_widget_message_document_title">تطبيق درع التعافي .apk</div>
 <div class="tgme_widget_message_text js-message_text">يحجب الكلمات والمواقع المحرمة.<br/>مجاني بالكامل.
  <a href="https://t.me/s/muslim_appss?q=%23x">#x</a> <a href="https://youtu.be/abc">شرح</a></div>
 <time datetime="2026-10-20T21:33:00+00:00">21:33</time>
</div>
<div class="tgme_widget_message" data-post="muslim_appss/646">
 <div class="tgme_widget_message_text js-message_text">الرفيق الإسلامي إضافة متصفح فيها مواقيت صلاة وبحث قرآني وحاجب صور.</div>
</div>
<div class="tgme_widget_message" data-post="muslim_appss/647"></div>
"""


def make_db(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    for p in parse_posts(HTML, "muslim_appss"):
        index_post(db, p)
    return db


def test_parse_posts():
    posts = parse_posts(HTML, "muslim_appss")
    assert [p.id for p in posts] == [640, 646, 647]
    assert "ملف: تطبيق درع التعافي" in posts[0].text
    assert "https://youtu.be/abc" in posts[0].text and "q=%23" not in posts[0].text
    assert posts[0].url == "https://t.me/muslim_appss/640"


def test_search_finds_right_post(tmp_path):
    db = make_db(tmp_path)
    top = db.search(query_tokens("عايز تطبيق يحجب المواقع"), 3)
    assert top and top[0]["post_id"] == 640
    top = db.search(query_tokens("اضافة متصفح مواقيت الصلاة"), 3)
    assert top[0]["post_id"] == 646


def test_reindex_replaces_old_chunks(tmp_path):
    db = make_db(tmp_path)
    p = parse_posts(HTML, "muslim_appss")[1]
    p.text = "نص جديد تمامًا عن تطبيق الأذكار"
    index_post(db, p)
    assert db.search(query_tokens("اذكار"), 3)[0]["post_id"] == 646
    assert not [r for r in db.search(query_tokens("حاجب صور"), 3) if r["post_id"] == 646]


def test_chunking():
    assert len(chunk_text("س" * 2000)) == 3
    assert chunk_text("a\n\nb") == ["a\nb"]


def test_group_doc_pair():
    d = group_doc("muslimappss", 5, "جرب تطبيق كذا", "عايز تطبيق للأذكار؟", True)
    assert d["body"].startswith("سؤال:") and d["trust"] == 2
