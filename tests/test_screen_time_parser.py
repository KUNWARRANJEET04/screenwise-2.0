from screenwise.extraction.screen_time_parser import (
    canonical_app_category,
    is_screen_time_ocr,
    parse_duration_seconds,
    parse_screen_time_text,
)


def test_parse_duration_formats():
    assert parse_duration_seconds("2h 52m") == 10320
    assert parse_duration_seconds("20h 6m") == 72360
    assert parse_duration_seconds("43m") == 2580
    assert parse_duration_seconds("1 hr") == 3600
    assert parse_duration_seconds("1 hr 20 min") == 4800


def test_parse_weekly_screen_time_example_and_category_pairing():
    text = """
    Screen Time
    Show This Week
    Last Week's Average
    2h 52m
    Entertainment
    Social
    Creativity
    8h 24m
    4h 43m
    1h 23m
    Total Screen Time
    20h 6m
    Most Used
    Safari
    7h 17m
    YouTube
    8>
    4h 25m
    WhatsApp
    4h 12m
    """
    result = parse_screen_time_text(text)
    assert result["total_screen_time_seconds"] == 20 * 3600 + 6 * 60
    assert result["average_seconds"] == 2 * 3600 + 52 * 60
    assert [(c.category_name, c.duration_seconds) for c in result["category_usage"]] == [
        ("Entertainment", 8 * 3600 + 24 * 60),
        ("Social", 4 * 3600 + 43 * 60),
        ("Creativity", 1 * 3600 + 23 * 60),
    ]
    apps = {a.app_name: a for a in result["app_usage"]}
    assert apps["Safari"].duration_seconds == 7 * 3600 + 17 * 60
    assert apps["YouTube"].duration_seconds == 4 * 3600 + 25 * 60
    assert apps["WhatsApp"].duration_seconds == 4 * 3600 + 12 * 60
    assert apps["YouTube"].category == "Entertainment"
    assert apps["WhatsApp"].category == "Social"


def test_known_app_categories():
    assert canonical_app_category("Instagram") == "Social"
    assert canonical_app_category("YouTube") == "Entertainment"
    assert canonical_app_category("Safari") == "Information & Reading"
    assert canonical_app_category("An unknown app") == "Unclassified"


def test_parse_pickups_count():
    result = parse_screen_time_text(
        "Screen Time\nTotal Pickups\n282\nNotifications\n120"
    )
    assert result["pickups"].total_pickups == 282
    assert result["pickups"].notifications == 120


def test_empty_text_does_not_invent_values():
    result = parse_screen_time_text("")
    assert result["app_usage"] == []
    assert result["category_usage"] == []
    assert result["pickups"] is None
    assert result["total_screen_time_seconds"] is None


def test_non_screen_time_text_is_rejected():
    accepted, _ = is_screen_time_ocr("A photo of a dog in a park")
    assert not accepted


def test_screen_time_evidence_is_accepted():
    accepted, evidence = is_screen_time_ocr(
        "Screen Time\nMost Used\nYouTube\n2h 10m"
    )
    assert accepted
    assert "screen time" in evidence
    assert "most used" in evidence
