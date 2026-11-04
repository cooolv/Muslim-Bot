from bot.arabic import index_text, normalize, query_tokens, fts_query


def test_normalize_diacritics_and_letters():
    assert normalize("أَحْمَد") == "احمد"
    assert normalize("مدرسة") == "مدرسه"
    assert normalize("على") == "علي"
    assert normalize("١٢٣") == "123"


def test_stemming_matches_plural_and_article():
    assert "حجب" in index_text("الحجب").split()
    assert index_text("الصلوات") == index_text("صلوات")
    assert query_tokens("التطبيقات") == []  # كلمة عامة تُهمل


def test_stopwords_removed_and_query_built():
    toks = query_tokens("عايز تطبيق يحجب المواقع")
    assert "عايز" not in toks and "يحجب" in toks
    assert fts_query(toks).count("OR") == len(toks) - 1
