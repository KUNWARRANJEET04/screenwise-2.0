from __future__ import annotations

import re
from typing import Optional

from screenwise.schemas.usage import AppUsage, CategoryUsage, PickupMetrics

# Explicit, editable rules. Unknown apps remain Unclassified rather than guessed.
APP_CATEGORY_MAP = {
    "youtube": "Entertainment",
    "youtube music": "Entertainment",
    "netflix": "Entertainment",
    "prime video": "Entertainment",
    "amazon prime video": "Entertainment",
    "disney+": "Entertainment",
    "hotstar": "Entertainment",
    "spotify": "Entertainment",
    "apple music": "Entertainment",
    "twitch": "Entertainment",
    "tiktok": "Entertainment",
    "instagram": "Social",
    "whatsapp": "Social",
    "facebook": "Social",
    "messenger": "Social",
    "snapchat": "Social",
    "telegram": "Social",
    "discord": "Social",
    "reddit": "Social",
    "x": "Social",
    "twitter": "Social",
    "linkedin": "Social",
    "threads": "Social",
    "safari": "Information & Reading",
    "google chrome": "Information & Reading",
    "chrome": "Information & Reading",
    "firefox": "Information & Reading",
    "books": "Information & Reading",
    "kindle": "Information & Reading",
    "google": "Information & Reading",
    "gmail": "Productivity & Finance",
    "outlook": "Productivity & Finance",
    "microsoft teams": "Productivity & Finance",
    "teams": "Productivity & Finance",
    "slack": "Productivity & Finance",
    "notion": "Productivity & Finance",
    "calendar": "Productivity & Finance",
    "google calendar": "Productivity & Finance",
    "microsoft excel": "Productivity & Finance",
    "excel": "Productivity & Finance",
    "microsoft word": "Productivity & Finance",
    "word": "Productivity & Finance",
    "google drive": "Productivity & Finance",
    "files": "Utilities",
    "settings": "Utilities",
    "clock": "Utilities",
    "calculator": "Utilities",
    "app store": "Utilities",
    "phone": "Social",
    "messages": "Social",
    "facetime": "Social",
    "health": "Health & Fitness",
    "fitness": "Health & Fitness",
    "maps": "Travel",
    "google maps": "Travel",
    "uber": "Travel",
}

KNOWN_CATEGORIES = {
    "social": "Social",
    "entertainment": "Entertainment",
    "creativity": "Creativity",
    "productivity & finance": "Productivity & Finance",
    "productivity": "Productivity & Finance",
    "information & reading": "Information & Reading",
    "information": "Information & Reading",
    "health & fitness": "Health & Fitness",
    "health": "Health & Fitness",
    "travel": "Travel",
    "utilities": "Utilities",
    "other": "Other",
}

DURATION_RE = re.compile(
    r"^\s*(?:(?P<hours>\d+(?:\.\d+)?)\s*h(?:ours?)?)?"
    r"\s*(?:(?P<minutes>\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?\s*$",
    re.IGNORECASE,
)
ALT_DURATION_RE = re.compile(
    r"^\s*(?:(?P<hours>\d+(?:\.\d+)?)\s*hr(?:s)?)?"
    r"\s*(?:(?P<minutes>\d+(?:\.\d+)?)\s*min(?:s)?)?\s*$",
    re.IGNORECASE,
)
COMPACT_DURATION_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d{2})\s*$")

STOP_LABELS = {
    "screen time", "show this week", "show today", "show categories",
    "most used", "total screen time", "updated today", "updated yesterday",
    "limits", "notifications", "pickups", "devices", "week", "day",
    "last week's average", "last week average", "this week", "today",
    "all activity", "see all activity",
}

def canonical_app_category(app_name: str) -> str:
    key = re.sub(r"\s+", " ", app_name.strip().lower())
    return APP_CATEGORY_MAP.get(key, "Unclassified")

def parse_duration_seconds(value: str) -> int | None:
    text = value.strip().lower().replace(",", "")
    if not text:
        return None
    compact = COMPACT_DURATION_RE.match(text)
    if compact:
        minutes, seconds = int(compact.group(1)), int(compact.group(2))
        if seconds < 60:
            return minutes * 60 + seconds
    for pattern in (DURATION_RE, ALT_DURATION_RE):
        match = pattern.match(text)
        if match and (match.group("hours") or match.group("minutes")):
            hours = float(match.group("hours") or 0)
            minutes = float(match.group("minutes") or 0)
            if hours < 0 or minutes < 0 or minutes >= 60:
                return None
            return int(round(hours * 3600 + minutes * 60))
    return None

def _clean_lines(text: str) -> list[str]:
    output = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip().replace("›", " ")).strip()
        if not line or line in {">", "<", "|", "•", "·"}:
            continue
        output.append(line)
    return output

def _find_duration_after(lines: list[str], index: int, lookahead: int = 3) -> int | None:
    for candidate in lines[index + 1:index + 1 + lookahead]:
        seconds = parse_duration_seconds(candidate)
        if seconds is not None:
            return seconds
    return None

def _parse_total_and_average(lines: list[str]) -> tuple[int | None, int | None]:
    total = average = None
    for i, line in enumerate(lines):
        low = line.lower()
        if "total screen time" in low:
            total = parse_duration_seconds(line) or _find_duration_after(lines, i, 3)
        if "last week's average" in low or "last week average" in low:
            average = parse_duration_seconds(line) or _find_duration_after(lines, i, 3)
    return total, average

def _parse_categories(lines: list[str]) -> list[CategoryUsage]:
    # iOS often emits all category names followed by all their values.
    positions = [(i, KNOWN_CATEGORIES[line.lower()]) for i, line in enumerate(lines)
                 if line.lower() in KNOWN_CATEGORIES]
    if not positions:
        return []
    first, last = positions[0][0], positions[-1][0]
    names = [name for _, name in positions]
    durations = []
    for line in lines[last + 1:]:
        if line.lower() in STOP_LABELS or line.lower() == "most used":
            break
        value = parse_duration_seconds(line)
        if value is not None:
            durations.append(value)
        # Stop after collecting enough values; later OCR may contain app rows.
        if len(durations) >= len(names):
            break
    pairs = []
    if len(durations) == len(names):
        pairs = list(zip(names, durations))
    else:
        # Fallback for label/value interleaving. Only accept a close, unique value.
        for index, name in positions:
            value = _find_duration_after(lines, index, 2)
            if value is not None:
                pairs.append((name, value))
    merged: dict[str, int] = {}
    for name, seconds in pairs:
        merged[name] = seconds
    return [CategoryUsage(category_name=k, duration_seconds=v) for k, v in merged.items()]

def _is_ui_label(value: str) -> bool:
    low = value.lower().strip()
    return (
        low in STOP_LABELS
        or low in KNOWN_CATEGORIES
        or low.startswith(("show ", "updated ", "total ", "last week"))
        or bool(re.fullmatch(r"[\W\d_]+", value))
        or len(value) > 55
        or not re.search(r"[A-Za-z]", value)
    )

def _parse_apps(lines: list[str]) -> list[AppUsage]:
    try:
        start = next(i for i, line in enumerate(lines) if line.lower() == "most used")
    except StopIteration:
        return []
    tail = lines[start + 1:]
    apps: dict[str, int] = {}
    for i, line in enumerate(tail):
        name = line.strip()
        if _is_ui_label(name) or parse_duration_seconds(name) is not None:
            continue
        # OCR can put chevrons or a tiny "8>" marker between the app and time.
        duration = _find_duration_after(tail, i, 4)
        if duration is None:
            continue
        # Do not treat a number/metric or an adjacent interface heading as an app.
        if name.lower() in {"screen time", "devices", "week", "day"}:
            continue
        apps[name] = duration
    return [
        AppUsage(app_name=name, duration_seconds=seconds,
                 category=canonical_app_category(name))
        for name, seconds in apps.items()
    ]

def _parse_count_after_label(lines: list[str], labels: tuple[str, ...]) -> int | None:
    for i, line in enumerate(lines):
        low = line.lower()
        if any(label in low for label in labels):
            inline = re.search(r"\b(\d{1,6})\b", line)
            if inline:
                return int(inline.group(1))
            for candidate in lines[i + 1:i + 4]:
                match = re.fullmatch(r"\s*(\d{1,6})\s*", candidate)
                if match:
                    return int(match.group(1))
    return None

def is_screen_time_ocr(text: str) -> tuple[bool, list[str]]:
    """Conservative OCR-content check; returns (accepted, evidence labels)."""
    low = re.sub(r"\s+", " ", text.lower())
    checks = {
        "screen time": "screen time" in low,
        "most used": "most used" in low,
        "total screen time": "total screen time" in low,
        "pickups": "pickups" in low,
        "show this week": "show this week" in low,
        "last week's average": "last week's average" in low or "last week average" in low,
        "category labels": any(name in low for name in KNOWN_CATEGORIES),
    }
    evidence = [label for label, found in checks.items() if found]
    accepted = (
        checks["screen time"] and len(evidence) >= 2
    ) or (checks["most used"] and len(evidence) >= 2) or (
        checks["total screen time"] and len(evidence) >= 2
    )
    return accepted, evidence

def parse_screen_time_text(text: str) -> dict:
    lines = _clean_lines(text)
    total_seconds, average_seconds = _parse_total_and_average(lines)
    categories = _parse_categories(lines)
    apps = _parse_apps(lines)
    pickups_count = _parse_count_after_label(lines, ("total pickups", "pickups"))
    notifications_count = _parse_count_after_label(lines, ("notifications",))
    pickups = PickupMetrics(total_pickups=pickups_count, notifications=notifications_count) if pickups_count is not None else None
    warnings = []
    if not apps:
        warnings.append("No app-level durations were confidently parsed from the OCR text.")
    if not categories:
        warnings.append("No category-level durations were confidently parsed from the OCR text.")
    if total_seconds is None:
        warnings.append("Total Screen Time was not confidently identified.")
    if average_seconds is None:
        warnings.append("The displayed average was not identified.")
    return {
        "app_usage": apps,
        "category_usage": categories,
        "pickups": pickups,
        "total_screen_time_seconds": total_seconds,
        "average_seconds": average_seconds,
        "warnings": warnings,
    }
