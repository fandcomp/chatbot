from app.chunking.contextual_text import render_contextual_text


def test_render_contextual_text_for_article_grammar_path():
    path = [
        {"node_type": "CHAPTER", "label": "BAB III", "title": None},
        {"node_type": "ARTICLE", "label": "Pasal 20", "title": None},
    ]

    text = render_contextual_text("Peraturan Contoh Nomor 2 Tahun 2026", path, "isi pasal")

    assert "Dokumen:" in text
    assert "Peraturan Contoh Nomor 2 Tahun 2026" in text
    assert "BAB III" in text
    assert "Pasal 20" in text
    assert "Isi:" in text
    assert text.endswith("isi pasal")


def test_render_contextual_text_for_numbered_section_grammar_never_fabricates_pasal():
    path = [
        {"node_type": "CHAPTER", "label": "BAB III", "title": None},
        {"node_type": "NUMBERED_SECTION", "label": "11. Urut-urutan Kegiatan", "title": None},
    ]

    text = render_contextual_text("SOP Contoh", path, "isi")

    assert "11. Urut-urutan Kegiatan" in text
    assert "Pasal" not in text


def test_render_contextual_text_with_no_ancestors_still_includes_dokumen_and_isi():
    text = render_contextual_text("Dokumen Bebas", [], "isi bebas")

    assert text.startswith("Dokumen:\nDokumen Bebas")
    assert text.endswith("isi bebas")
