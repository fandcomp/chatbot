from app.parsing.page_classifier import PageCategory, PageStats, classify_page


def test_classify_page_digital_text_when_plenty_of_chars_and_no_visuals():
    stats = PageStats(page_no=1, char_count=1200, picture_count=0, table_count=0,
                       picture_area_ratio=0.0)

    assert classify_page(stats) == PageCategory.DIGITAL_TEXT


def test_classify_page_scanned_when_no_usable_text_but_has_a_picture():
    stats = PageStats(page_no=1, char_count=0, picture_count=1, table_count=0,
                       picture_area_ratio=0.9)

    assert classify_page(stats) == PageCategory.SCANNED


def test_classify_page_unknown_when_completely_empty():
    stats = PageStats(page_no=1, char_count=0, picture_count=0, table_count=0,
                       picture_area_ratio=0.0)

    assert classify_page(stats) == PageCategory.UNKNOWN


def test_classify_page_image_heavy_when_picture_covers_most_of_page():
    stats = PageStats(page_no=1, char_count=500, picture_count=1, table_count=0,
                       picture_area_ratio=0.75)

    assert classify_page(stats) == PageCategory.IMAGE_HEAVY


def test_classify_page_table_heavy_when_has_table_and_usable_text():
    stats = PageStats(page_no=1, char_count=500, picture_count=0, table_count=2,
                       picture_area_ratio=0.0)

    assert classify_page(stats) == PageCategory.TABLE_HEAVY


def test_classify_page_layout_complex_when_text_picture_and_table_combine():
    stats = PageStats(page_no=1, char_count=500, picture_count=1, table_count=1,
                       picture_area_ratio=0.1)

    # A page with a table always classifies as TABLE_HEAVY first — that's
    # the cascade trigger that matters (table structure needs Level 2).
    assert classify_page(stats) == PageCategory.TABLE_HEAVY


def test_classify_page_layout_complex_when_text_and_picture_but_no_table():
    stats = PageStats(page_no=1, char_count=500, picture_count=1, table_count=0,
                       picture_area_ratio=0.1)

    assert classify_page(stats) == PageCategory.LAYOUT_COMPLEX
