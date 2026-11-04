from datetime import datetime

from bot.prayer import due_prayers, reminder_text

T = {"Fajr": "04:45", "Dhuhr": "11:55", "Asr": "15:10", "Maghrib": "17:40", "Isha": "19:00"}


def test_due_window():
    assert due_prayers(T, datetime(2026, 11, 4, 15, 10, 30)) == ["Asr"]
    assert due_prayers(T, datetime(2026, 11, 4, 15, 13, 0)) == []
    assert due_prayers(T, datetime(2026, 11, 4, 15, 9, 59)) == []


def test_lead_minutes():
    assert due_prayers(T, datetime(2026, 11, 4, 15, 5, 10), lead_min=5) == ["Asr"]


def test_reminder_text():
    t = reminder_text("أحمد", "Fajr", "04:45", "الإسماعيلية", 0)
    assert "أحمد" in t and "الفجر" in t and "الصلاة خير من النوم" in t
    assert "باقي 10 دقيقة" in reminder_text("", "Asr", "15:10", "القاهرة", 10)
