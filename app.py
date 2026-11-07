from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from PIL import Image, UnidentifiedImageError

import os
import streamlit as st

if "AZURE_VISION_ENDPOINT" in st.secrets:
    os.environ["AZURE_VISION_ENDPOINT"] = st.secrets[
        "AZURE_VISION_ENDPOINT"
    ]

if "AZURE_VISION_KEY" in st.secrets:
    os.environ["AZURE_VISION_KEY"] = st.secrets[
        "AZURE_VISION_KEY"
    ]

from screenwise.config import settings

from screenwise.config import settings
from screenwise.extraction.pipeline import process_screenshot
from screenwise.extraction.screen_time_parser import parse_screen_time_text
from screenwise.ingestion.screenshot_ingestor import ingest_image
from screenwise.metadata import filename_metadata
from screenwise.schemas.common import ExtractionStatus, ValidationStatus


# ---------------------------------------------------------------------
# Page setup and visual theme
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="ScreenWise | Usage Intelligence",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("screenwise.ui")

SCREENSHOT_ERROR = (
    "Please upload a relevant iPhone Screen Time or "
    "Android Digital Wellbeing screenshot."
)

REVIEW_MESSAGE = (
    "This image may contain screen-usage information, "
    "but ScreenWise could not identify it confidently. Please review it."
)
MAX_FILES = 5

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp {
      background:
        radial-gradient(circle at 8% 0%, rgba(91,110,225,.13), transparent 26%),
        radial-gradient(circle at 95% 5%, rgba(20,184,166,.09), transparent 23%),
        #0b1020;
    }
    [data-testid="stHeader"] { background: rgba(11,16,32,.78); }
    [data-testid="stSidebar"] {
      background: #10182b;
      border-right: 1px solid rgba(148,163,184,.14);
    }
    .block-container { max-width: 1480px; padding-top: 1.7rem; padding-bottom: 3rem; }
    .hero {
      padding: 1.8rem 2rem; border: 1px solid rgba(148,163,184,.18);
      border-radius: 22px;
      background: linear-gradient(120deg,rgba(30,41,74,.97),rgba(17,32,53,.95));
      margin-bottom: 1.5rem; box-shadow: 0 16px 40px rgba(0,0,0,.18);
    }
    .eyebrow, .kicker {
      color: #8ee6d4; font-size: .73rem; font-weight: 800;
      letter-spacing: .16em; text-transform: uppercase;
    }
    .hero-title {
      color: #f8fafc; font-size: clamp(2rem,4vw,3rem);
      line-height: 1.08; font-weight: 800; margin: .4rem 0;
    }
    .hero-copy { color: #b8c4d8; font-size: 1rem; max-width: 790px; }
    .section-title { color: #f8fafc; font-size: 1.35rem; font-weight: 800; margin-bottom: .15rem; }
    .section-copy { color: #94a3b8; font-size: .9rem; margin-bottom: .9rem; }
    .metric-card {
      background: linear-gradient(145deg,rgba(30,41,59,.97),rgba(19,29,49,.97));
      border: 1px solid rgba(148,163,184,.17); border-radius: 18px;
      padding: 1.05rem 1.15rem; min-height: 122px;
      box-shadow: 0 10px 24px rgba(0,0,0,.12);
    }
    .metric-label {
      color: #aab8ce; font-size: .76rem; font-weight: 700;
      letter-spacing: .04em; text-transform: uppercase;
    }
    .metric-value {
      color: #f8fafc; font-size: clamp(1.45rem,2.4vw,2.05rem);
      font-weight: 800; margin-top: .45rem; line-height: 1.1;
    }
    .metric-foot { color: #7ddbc9; font-size: .76rem; margin-top: .45rem; }
    .panel {
      background: rgba(18,28,47,.78); border: 1px solid rgba(148,163,184,.15);
      border-radius: 18px; padding: 1rem 1.1rem;
    }
    div[data-testid="stMetric"] {
      background: rgba(20,31,52,.78); border: 1px solid rgba(148,163,184,.15);
      padding: .85rem 1rem; border-radius: 14px;
    }
    div[data-testid="stMetricLabel"] { color: #aab8ce; }
    div[data-testid="stMetricValue"] { color: #f8fafc; }
    .stButton>button[kind="primary"] {
      border-radius: 12px; font-weight: 800; min-height: 2.8rem;
      border: 0; background: linear-gradient(90deg,#14b8a6,#3b82f6);
    }
    .stButton>button { border-radius: 10px; }
    div[data-testid="stFileUploader"] {
      background: rgba(20,31,52,.55); border: 1px dashed rgba(125,211,252,.35);
      border-radius: 15px; padding: .8rem;
    }
    .sw-pill {
      display: inline-block; border: 1px solid #3a4665; color: #c9c4ff;
      background: #201d3e; border-radius: 999px; padding: 4px 10px;
      font-size: .75rem; font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def heading(kicker: str, title: str, copy: str = "") -> None:
    st.markdown(
        f'<div class="kicker">{kicker}</div>'
        f'<div class="section-title">{title}</div>'
        f'<div class="section-copy">{copy}</div>',
        unsafe_allow_html=True,
    )


def fmt_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def metric_card(label: str, value: str, foot: str = "") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-foot">{foot}</div></div>',
        unsafe_allow_html=True,
    )


def safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def model_to_dict(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def get_upload_metadata(files: list[Any], fallback_subject: str, fallback_session: str) -> list[dict]:
    """Build the participant/session preview before any OCR is run."""
    rows = []
    for uploaded in files:
        subject, session = filename_metadata(Path(uploaded.name).name)
        rows.append({
            "filename": Path(uploaded.name).name,
            "subject_id": subject or fallback_subject.strip() or "subject-unassigned",
            "session_id": session or fallback_session.strip() or "session-unassigned",
            "subject_from_filename": bool(subject),
            "session_from_filename": bool(session),
        })
    return rows


def validate_uploads(files: list[Any]) -> tuple[list[dict], int, int]:
    valid, seen = [], set()
    duplicates = invalid = 0

    for uploaded in files:
        raw = uploaded.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)

        try:
            image = Image.open(io.BytesIO(raw))
            image.verify()
            image = Image.open(io.BytesIO(raw))
            image.load()
            if image.width < 100 or image.height < 100:
                invalid += 1
                continue
            valid.append({
                "name": Path(uploaded.name).name,
                "bytes": raw,
                "image": image.convert("RGB").copy(),
                "width": image.width,
                "height": image.height,
                "sha256": digest,
            })
        except (UnidentifiedImageError, OSError, ValueError):
            invalid += 1

    return valid, duplicates, invalid


def profile_key(subject_id: str) -> str:
    return f"screenwise_profile_{safe_key(subject_id)}"


def get_profile(subject_id: str) -> dict:
    return st.session_state.setdefault(
        profile_key(subject_id),
        {"label": "", "cohort": "", "notes": ""},
    )

def detect_screen_platform(ocr_text: str) -> dict:
    """
    Identify iPhone Screen Time or Android Digital Wellbeing screenshots
    using multiple independent OCR signals.

    Returns:
        {
            "platform": "iPhone" | "Android" | "Unknown",
            "decision": "accept" | "review" | "reject",
            "evidence": list[str],
            "reason": str,
        }

    Pickups are an optional iPhone-specific metric, never an Android
    validation requirement.
    """
    text = re.sub(r"\s+", " ", (ocr_text or "").lower()).strip()

    if not text:
        return {
            "platform": "Unknown",
            "decision": "reject",
            "evidence": [],
            "reason": "No readable screen-usage text was recognised.",
        }

    # iPhone / Apple Screen Time indicators
    ios_signals = {
        "screen_time": bool(re.search(r"\bscreen\s*time\b", text)),
        "most_used": bool(re.search(r"\bmost\s+used\b", text)),
        "last_week_average": bool(
            re.search(r"last\s+week.?s?\s+average", text)
        ),
        "pickups": bool(re.search(r"\bpickups?\b", text)),
        "notifications": bool(re.search(r"\bnotifications?\b", text)),
        "downtime": bool(re.search(r"\bdowntime\b", text)),
        "app_limits": bool(re.search(r"\bapp\s+limits?\b", text)),
        "always_allowed": bool(re.search(r"\balways\s+allowed\b", text)),
        "share_devices": bool(
            re.search(r"share\s+across\s+devices", text)
        ),
        "first_used_after_pickup": bool(
            re.search(r"first\s+used\s+after\s+pickup", text)
        ),
    }

    # Android Digital Wellbeing / common Android manufacturer indicators
    android_signals = {
        "digital_wellbeing": bool(
            re.search(r"digital\s+wellbeing", text)
        ),
        "digital_balance": bool(
            re.search(r"digital\s+balance", text)
        ),
        "dashboard": bool(re.search(r"\bdashboard\b", text)),
        "app_timers": bool(re.search(r"app\s+timers?", text)),
        "unlock_count": bool(
            re.search(r"\b(unlocks?|times?\s+unlocked)\b", text)
        ),
        "bedtime_mode": bool(re.search(r"bedtime\s+mode", text)),
        "focus_mode": bool(re.search(r"focus\s+mode", text)),
        "parental_controls": bool(
            re.search(r"parental\s+controls?", text)
        ),
        "app_usage": bool(
            re.search(r"\bapp\s+usage\b|\btime\s+spent\b", text)
        ),
        "screen_time": bool(re.search(r"\bscreen\s*time\b", text)),
        "daily_average": bool(
            re.search(r"daily\s+average|average\s+daily", text)
        ),
        "notifications": bool(re.search(r"\bnotifications?\b", text)),
    }

    # Generic usage indicators useful across Android manufacturers.
    generic_usage_signals = {
        "app_usage": bool(
            re.search(r"\bapp\s+usage\b|\bmost\s+used\b", text)
        ),
        "daily_average": bool(
            re.search(r"daily\s+average|average\s+daily", text)
        ),
        "screen_time": bool(re.search(r"\bscreen\s*time\b", text)),
        "time_spent": bool(re.search(r"\btime\s+spent\b", text)),
        "usage_dashboard": bool(
            re.search(r"\busage\s+dashboard\b", text)
        ),
    }

    ios_evidence = [
        name for name, found in ios_signals.items() if found
    ]
    android_evidence = [
        name for name, found in android_signals.items() if found
    ]

    ios_brand = any(
        ios_signals[key]
        for key in ("screen_time", "last_week_average", "share_devices")
    )
    ios_distinctive = sum(
        ios_signals[key]
        for key in (
            "most_used",
            "pickups",
            "notifications",
            "downtime",
            "app_limits",
            "always_allowed",
            "first_used_after_pickup",
        )
    )

    android_brand = any(
        android_signals[key]
        for key in (
            "digital_wellbeing",
            "digital_balance",
            "parental_controls",
        )
    )
    android_distinctive = sum(
        android_signals[key]
        for key in (
            "dashboard",
            "app_timers",
            "unlock_count",
            "bedtime_mode",
            "focus_mode",
            "app_usage",
            "daily_average",
            "notifications",
        )
    )

    # Strong iPhone evidence.
    # A pickups-only page can qualify when accompanied by another
    # characteristic Screen Time indicator.
    ios_pickups_page = (
        ios_signals["pickups"]
        and (
            ios_signals["notifications"]
            or ios_signals["first_used_after_pickup"]
            or ios_signals["most_used"]
            or ios_signals["last_week_average"]
        )
    )

    if (ios_brand and ios_distinctive >= 1) or ios_pickups_page:
        return {
            "platform": "iPhone",
            "decision": "accept",
            "evidence": ios_evidence,
            "reason": "Multiple iPhone Screen Time indicators were recognised.",
        }

    # Strong Android evidence.
    if android_brand and android_distinctive >= 1:
        return {
            "platform": "Android",
            "decision": "accept",
            "evidence": android_evidence,
            "reason": "Android Digital Wellbeing indicators were recognised.",
        }

    # Android screens that omit the product heading can still be
    # recognised when several independent dashboard signals exist.
    if (
        android_signals["dashboard"]
        and android_distinctive >= 2
    ):
        return {
            "platform": "Android",
            "decision": "accept",
            "evidence": android_evidence,
            "reason": "Multiple Android usage-dashboard indicators were recognised.",
        }

    # Generic phone-usage layout: accept only with multiple independent
    # indicators. Do not accept a single occurrence of "screen time".
    generic_count = sum(generic_usage_signals.values())

    if generic_count >= 3:
        return {
            "platform": "Unknown",
            "decision": "accept",
            "evidence": [
                name for name, found in generic_usage_signals.items() if found
            ],
            "reason": "A phone screen-usage dashboard was recognised, but its platform is unclear.",
        }

    # A small amount of relevant OCR evidence should be reviewed rather
    # than immediately treated as a photograph of an unrelated object.
    possible_usage_content = (
        ios_distinctive >= 1
        or android_distinctive >= 1
        or generic_count >= 1
    )

    if possible_usage_content:
        return {
            "platform": "Unknown",
            "decision": "review",
            "evidence": sorted(set(ios_evidence + android_evidence)),
            "reason": "Some screen-usage indicators were found, but there is not enough evidence to confirm the screenshot.",
        }

    # Ordinary photographs, documents, animals, carpets, landscapes,
    # and other unrelated images should normally end up here.
    return {
        "platform": "Unknown",
        "decision": "reject",
        "evidence": [],
        "reason": "No meaningful phone screen-usage indicators were recognised.",
    }

def process_files(
    valid_images: list[dict],
    metadata_by_filename: dict[str, dict],
    study_label: str,
) -> list[dict]:
    records: list[dict] = []

    progress = st.progress(0, text="Preparing screenshots...")
    status = st.empty()

    for index, item in enumerate(valid_images):
        filename = item["name"]
        metadata = metadata_by_filename[filename]

        status.info(
            f"Analysing {index + 1}/{len(valid_images)} · {filename}"
        )

        try:
            ingestion = ingest_image(item["bytes"], filename)
            extraction = process_screenshot(ingestion.screenshot)

            ocr_text = extraction.raw_ocr_text or ""

            # Identify platform and validate screenshot relevance.
            validation = detect_screen_platform(ocr_text)

            common_record = {
                "filename": filename,
                "subject_id": metadata["subject_id"],
                "session_id": metadata["session_id"],
                "study_label": study_label,
                "platform": validation["platform"],
                "validation_evidence": validation["evidence"],
                "validation_reason": validation["reason"],
                "raw_ocr_text": ocr_text,
                "preview_bytes": item["bytes"],
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }

            if validation["decision"] == "reject":
                records.append({
                    **common_record,
                    "status": "rejected",
                    "error": SCREENSHOT_ERROR,
                })

                progress.progress(
                    (index + 1) / len(valid_images),
                    text=f"Checked {index + 1} of {len(valid_images)}",
                )
                continue

            if validation["decision"] == "review":
                records.append({
                    **common_record,
                    "status": "review",
                    "error": REVIEW_MESSAGE,
                })

                progress.progress(
                    (index + 1) / len(valid_images),
                    text=f"Checked {index + 1} of {len(valid_images)}",
                )
                continue

            # Add participant metadata only after validation.
            extraction.metadata.subject_id = metadata["subject_id"]
            extraction.metadata.session_id = metadata["session_id"]

            # Existing parser is used for recognised app/category data.
            parsed = parse_screen_time_text(ocr_text)

            extraction.app_usage = parsed["app_usage"]
            extraction.category_usage = parsed["category_usage"]

            # Pickups are an iPhone-specific metric in this application.
            # Never populate Android pickups from an accidental OCR match.
            if validation["platform"] == "iPhone":
                extraction.pickups = parsed["pickups"]
            else:
                extraction.pickups = None

            warnings = list(extraction.warnings or [])

            for warning in parsed["warnings"]:
                if warning not in warnings:
                    warnings.append(warning)

            if validation["platform"] == "Unknown":
                warnings.append(
                    "Phone-usage screenshot recognised, but the platform "
                    "could not be identified confidently."
                )

            if validation["platform"] == "Android":
                warnings.append(
                    "Android screenshot recognised. Review the extracted "
                    "app and category values because Android layouts vary "
                    "between manufacturers."
                )

            extraction.warnings = list(dict.fromkeys(warnings))

            has_data = bool(
                extraction.app_usage
                or extraction.category_usage
                or (
                    validation["platform"] == "iPhone"
                    and extraction.pickups is not None
                )
                or parsed.get("total_screen_time_seconds") is not None
                or parsed.get("average_seconds") is not None
            )

            extraction.extraction_status = (
                ExtractionStatus.COMPLETE
                if has_data and not extraction.warnings
                else ExtractionStatus.PARTIAL
            )

            extraction.validation_status = ValidationStatus.NEEDS_REVIEW

            records.append({
                **common_record,
                "status": "accepted",
                "ingestion_status": ingestion.status.value,
                "ingestion_message": ingestion.message,
                "result": extraction,
                "parsed": parsed,
            })

        except Exception as exc:
            logger.exception("Failed to process %s", filename)

            records.append({
                "filename": filename,
                "subject_id": metadata["subject_id"],
                "session_id": metadata["session_id"],
                "study_label": study_label,
                "status": "error",
                "error": str(exc),
                "preview_bytes": item["bytes"],
                "processed_at": datetime.now(timezone.utc).isoformat(),
            })

        progress.progress(
            (index + 1) / len(valid_images),
            text=f"Processed {index + 1} of {len(valid_images)} screenshots",
        )

    status.empty()
    progress.empty()

    return records


def accepted_records(records: list[dict]) -> list[dict]:
    return [
        row for row in records
        if row.get("status") == "accepted"
        and row.get("result") is not None
    ]


def app_usage_frame(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        for app in record["result"].app_usage:
            rows.append({
                "Subject": record["subject_id"],
                "Session": record["session_id"],
                "Screenshot": record["filename"],
                "Application": app.app_name,
                "Category": app.category or "Unclassified",
                "Usage": fmt_duration(app.duration_seconds),
                "Minutes": round(app.duration_seconds / 60, 2),
            })
    return pd.DataFrame(rows)


def category_frame(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        for category in record["result"].category_usage:
            rows.append({
                "Subject": record["subject_id"],
                "Session": record["session_id"],
                "Screenshot": record["filename"],
                "Category": category.category_name,
                "Usage": fmt_duration(category.duration_seconds),
                "Minutes": round(category.duration_seconds / 60, 2),
            })
    return pd.DataFrame(rows)


def export_report(records: list[dict]) -> bytes:
    screenshots = []
    for record in records:
        row = {
            "filename": record["filename"],
            "subject_id": record.get("subject_id"),
            "session_id": record.get("session_id"),
            "study_label": record.get("study_label", ""),
            "status": record.get("status"),
            "processed_at": record.get("processed_at"),
            "platform": record.get("platform", "Unknown"),
            "validation_evidence": record.get("validation_evidence", []),
        }
        if record.get("result") is not None:
            row["extraction"] = model_to_dict(record["result"])
            row["parsed_summary"] = {
                "total_screen_time_seconds": record["parsed"].get("total_screen_time_seconds"),
                "average_seconds": record["parsed"].get("average_seconds"),
                "warnings": record["parsed"].get("warnings", []),
            }
        else:
            row["error"] = record.get("error")
            row["validation_evidence"] = record.get("validation_evidence", [])
            row["raw_ocr_text"] = record.get("raw_ocr_text", "")
        screenshots.append(row)

    subjects = sorted({r.get("subject_id") for r in records if r.get("subject_id")})
    profiles = {sid: get_profile(sid) for sid in subjects}
    return json.dumps({
        "application": "ScreenWise",
        "version": "2.1",
        "study_label": st.session_state.get("screenwise_study_label", ""),
        "subject_profiles": profiles,
        "screenshots": screenshots,
    }, indent=2, ensure_ascii=False).encode("utf-8")


def render_subject_dashboard(records: list[dict], subject_id: str) -> None:
    subject_records = [
        row for row in accepted_records(records)
        if row["subject_id"] == subject_id
    ]
    if not subject_records:
        return

    sessions = sorted({row["session_id"] for row in subject_records})
    profile = get_profile(subject_id)

    st.markdown(f"## Participant · `{subject_id}`")
    meta1, meta2, meta3 = st.columns(3)
    meta1.markdown(f"**Participant label**  \n{profile.get('label') or 'Not provided'}")
    meta2.markdown(f"**Cohort / group**  \n{profile.get('cohort') or 'Not provided'}")
    meta3.markdown(f"**Sessions**  \n{', '.join(sessions) if sessions else 'Not identified'}")

    selected_session = st.selectbox(
        "Session view",
        ["All sessions"] + sessions,
        key=f"dashboard_session_{safe_key(subject_id)}",
    )
    view = (
        subject_records if selected_session == "All sessions"
        else [row for row in subject_records if row["session_id"] == selected_session]
    )

    all_pickups = [
    row["result"].pickups.total_pickups
    for row in view
    if row.get("platform") == "iPhone"
    and row["result"].pickups is not None
    ]
    total_values = [
        row["parsed"].get("total_screen_time_seconds")
        for row in view if row["parsed"].get("total_screen_time_seconds") is not None
    ]
    average_values = [
        row["parsed"].get("average_seconds")
        for row in view if row["parsed"].get("average_seconds") is not None
    ]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Screenshots", str(len(view)), "Accepted screenshots in this view")
    with c2:
        metric_card("Total screen time", fmt_duration(max(total_values) if total_values else None),
                    "Highest displayed total; not summed")
    with c3:
        metric_card("Displayed average", fmt_duration(max(average_values) if average_values else None),
                    "Highest displayed average; not summed")
    with c4:
        metric_card(
            "Pickups",
            f"{max(all_pickups):,}" if all_pickups else "—",
            "Highest reported iPhone value; not summed",
        )

    overview_tab, apps_tab, categories_tab, records_tab, quality_tab = st.tabs(
        ["Overview", "App usage", "Categories", "Screenshots", "Data quality"]
    )

    apps = app_usage_frame(view)
    categories = category_frame(view)

    with overview_tab:
        left, right = st.columns([1.15, 1])
        with left:
            st.markdown("#### Most-used apps")
            if not apps.empty:
                chart = (
                    apps.groupby("Application", as_index=True)["Minutes"]
                    .max().sort_values(ascending=False).head(10)
                )
                st.bar_chart(chart, horizontal=True, height=300)
            else:
                st.info("No app-level durations were extracted.")
        with right:
            st.markdown("#### Category breakdown")
            if not categories.empty:
                chart = (
                    categories.groupby("Category", as_index=True)["Minutes"]
                    .max().sort_values(ascending=False)
                )
                st.bar_chart(chart, height=300)
            else:
                st.info("No category-level durations were extracted.")
        st.caption("Repeated values across screenshots are not added together; charts use the maximum reported value for each app or category.")

    with apps_tab:
        st.markdown("#### App usage with category labels")
        if apps.empty:
            st.info("No app-level usage is available.")
        else:
            st.dataframe(
                apps.drop(columns=["Minutes"]),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Download app usage CSV",
                apps.to_csv(index=False).encode("utf-8"),
                file_name=f"{safe_key(subject_id)}_app_usage.csv",
                mime="text/csv",
                key=f"download_apps_{safe_key(subject_id)}",
            )

    with categories_tab:
        st.markdown("#### Phone category usage")
        if categories.empty:
            st.info("No category-level usage is available.")
        else:
            st.dataframe(
                categories.drop(columns=["Minutes"]),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Download category usage CSV",
                categories.to_csv(index=False).encode("utf-8"),
                file_name=f"{safe_key(subject_id)}_category_usage.csv",
                mime="text/csv",
                key=f"download_categories_{safe_key(subject_id)}",
            )

    with records_tab:
        for index, record in enumerate(view):
            result = record["result"]
            with st.expander(
                f"{record['filename']} · {record['session_id']} · {result.extraction_status.value.upper()}",
                expanded=False,
            ):
                st.caption(
                    f"Platform: {record.get('platform', 'Unknown')} · "
                    f"Original file: {record['filename']} · "
                    f"Ingestion: {record.get('ingestion_status', 'unknown')}"
                )
                st.image(record["preview_bytes"], caption="Uploaded screenshot", use_container_width=True)
                m1, m2, m3 = st.columns(3)
                m1.metric("Total screen time", fmt_duration(record["parsed"].get("total_screen_time_seconds")))
                m2.metric("Displayed average", fmt_duration(record["parsed"].get("average_seconds")))
                m3.metric(
                    "Pickups",
                    (
                        str(result.pickups.total_pickups)
                        if record.get("platform") == "iPhone" and result.pickups
                        else "—"
                    ),
                )
                if result.confidence is not None:
                    st.progress(
                        max(0.0, min(1.0, float(result.confidence))),
                        text=f"Azure OCR confidence · {result.confidence:.1%}",
                    )
                for warning in result.warnings:
                    st.warning(warning)
                ocr_tab, json_tab = st.tabs(["Recognised OCR text", "Structured data"])
                with ocr_tab:
                    st.text_area(
                        "OCR text",
                        result.raw_ocr_text or "",
                        height=220,
                        key=f"ocr_{safe_key(subject_id)}_{index}",
                    )
                    if result.evidence:
                        evidence_rows = [{
                            "Text": item.raw_text,
                            "Field": item.field_path,
                            "Bounding box": str(item.bounding_box) if item.bounding_box else "—",
                        } for item in result.evidence]
                        st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)
                with json_tab:
                    st.json(model_to_dict(result))

    with quality_tab:
        rows = []
        for record in view:
            result = record["result"]
            rows.append({
                "Screenshot": record["filename"],
                "OCR confidence": f"{result.confidence:.1%}" if result.confidence is not None else "Not available",
                "OCR lines": len(result.ocr_lines),
                "Apps extracted": len(result.app_usage),
                "Categories extracted": len(result.category_usage),
                "Warnings": len(result.warnings),
                "Status": result.extraction_status.value,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if any(row["Warnings"] for row in rows):
            st.warning("Some screenshots contain partial extraction results. Review the screenshot records and OCR text.")
        else:
            st.success("No parser warnings were reported for these screenshots.")


# ---------------------------------------------------------------------
# Sidebar: study and participant defaults
# ---------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📱 ScreenWise")
    st.caption("iPhone + Android Usage Intelligence · Azure OCR")
    st.divider()
    st.markdown("### Study information")
    study_label = st.text_input(
        "Study / project name",
        value=st.session_state.get("screenwise_study_label", ""),
        placeholder="e.g. Screen Time Study",
    )
    fallback_subject = st.text_input(
        "Default subject ID",
        placeholder="Used when filename has no sub-XXXXX",
    )
    fallback_session = st.text_input(
        "Default session ID",
        placeholder="Used when filename has no ses-XX",
    )
    st.caption("Subject and session IDs are automatically read from filenames when available.")
    st.divider()
    if settings.azure_vision_endpoint and settings.azure_vision_key:
        st.success("Azure Vision configured")
    else:
        st.error("Azure Vision configuration missing")
        st.caption("Set AZURE_VISION_ENDPOINT and AZURE_VISION_KEY in your .env file.")
    if st.button("Clear current analysis", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key.startswith(("screenwise_records", "screenwise_profile_", "dashboard_session_", "ocr_")):
                st.session_state.pop(key, None)
        st.rerun()


# ---------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Phone usage intelligence platform</div>
      <div class="hero-title">Understand your screen time.</div>
      <div class="hero-copy">
        Turn iPhone Screen Time screenshots into a structured view of app usage,
        category patterns, pickups and daily behaviour. Review participant details
        before running the analysis.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Upload and pre-analysis review
# ---------------------------------------------------------------------
heading(
    "01 · INPUT",
    "Upload your screenshots",
    "Add up to five iPhone Screen Time or Android Digital Wellbeing screenshots. You can include multiple participants; ScreenWise keeps their records separate.")

uploaded_files = st.file_uploader(
    "Choose phone-usage screenshots",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    help="Supports iPhone Screen Time and Android Digital Wellbeing screenshots. Maximum five files per batch.",)

valid_images: list[dict] = []
metadata_records: list[dict] = []
duplicate_count = invalid_count = 0

if uploaded_files:
    if len(uploaded_files) > MAX_FILES:
        st.error(f"Please upload no more than {MAX_FILES} screenshots in one batch.")
    else:
        valid_images, duplicate_count, invalid_count = validate_uploads(uploaded_files)
        metadata_records = get_upload_metadata(
            uploaded_files,
            fallback_subject,
            fallback_session,
        )
        # Only retain metadata for unique, valid images.
        valid_names = {item["name"] for item in valid_images}
        metadata_records = [row for row in metadata_records if row["filename"] in valid_names]
        metadata_by_filename = {row["filename"]: row for row in metadata_records}

        a, b, c, d = st.columns(4)
        a.metric("Uploaded", len(uploaded_files))
        b.metric("Valid images", len(valid_images))
        c.metric("Duplicates", duplicate_count)
        d.metric("Invalid", invalid_count)

        if duplicate_count:
            st.warning(f"{duplicate_count} duplicate screenshot(s) will be skipped.")
        if invalid_count:
            st.warning(f"{invalid_count} unreadable or invalid image(s) were skipped.")

        if valid_images:
            with st.expander(f"Preview screenshots ({len(valid_images)})", expanded=False):
                preview_cols = st.columns(3)
                for index, item in enumerate(valid_images):
                    with preview_cols[index % 3]:
                        st.image(item["image"], caption=item["name"], use_container_width=True)
                        st.caption(f"{item['width']} × {item['height']} pixels")

            # Participant metadata is deliberately shown before the Analyse button.
            heading(
                "02 · PARTICIPANT REVIEW",
                "Subject and session information",
                "Check the identifiers detected from each filename. Add participant labels or study notes before extraction."            )
            metadata_df = pd.DataFrame(metadata_records)
            if not metadata_df.empty:
                display_df = metadata_df.rename(columns={
                    "filename": "Screenshot",
                    "subject_id": "Subject ID",
                    "session_id": "Session ID",
                    "subject_from_filename": "Subject from filename",
                    "session_from_filename": "Session from filename",
                })
                st.dataframe(display_df, use_container_width=True, hide_index=True)

            subject_ids = sorted({row["subject_id"] for row in metadata_records})
            for subject_id in subject_ids:
                profile = get_profile(subject_id)
                with st.expander(f"Participant details · {subject_id}", expanded=True):
                    left, right = st.columns(2)
                    with left:
                        profile["label"] = st.text_input(
                            "Participant label (optional)",
                            value=profile.get("label", ""),
                            key=f"{profile_key(subject_id)}_label",
                        )
                        profile["cohort"] = st.text_input(
                            "Cohort / group (optional)",
                            value=profile.get("cohort", ""),
                            key=f"{profile_key(subject_id)}_cohort",
                        )
                    with right:
                        profile["notes"] = st.text_area(
                            "Participant notes (optional)",
                            value=profile.get("notes", ""),
                            height=92,
                            key=f"{profile_key(subject_id)}_notes",
                        )

            st.caption(
                "A valid image file is not automatically a valid Screen Time screenshot. "
                "ScreenWise checks the recognised content after Azure OCR."
            )

            st.divider()
            heading(
                "03 · EXTRACTION",
                "Build your report",
                "Each screenshot is processed individually. The results are then displayed in separate participant sections.",
            )
            azure_ready = bool(settings.azure_vision_endpoint and settings.azure_vision_key)
            can_analyse = bool(valid_images) and azure_ready and len(uploaded_files) <= MAX_FILES
            if not azure_ready:
                st.error("Azure Vision is not configured. Add the endpoint and key to .env, then restart Streamlit.")

            if st.button(
                "✨ Analyse screenshots",
                type="primary",
                use_container_width=True,
                disabled=not can_analyse,
            ):
                st.session_state["screenwise_study_label"] = study_label
                with st.spinner("Validating screenshots and extracting Screen Time data..."):
                    st.session_state["screenwise_records"] = process_files(
                        valid_images,
                        metadata_by_filename,
                        study_label,
                    )
                st.rerun()
else:
    st.markdown(
        """
        <div class="panel">
          <div class="kicker">Get started</div>
          <div class="section-title">Upload your Screen Time screenshots</div>
          <div class="section-copy">
            Add iPhone Screen Time or Android Digital Wellbeing screenshots.
            ScreenWise will validate the recognised content, show participant metadata,
            and then run Azure OCR.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------
records = st.session_state.get("screenwise_records", [])
if records:
    st.divider()
    heading(
        "04 · RESULTS",
        "Extraction summary",
        "Accepted screenshots are grouped by participant. Rejected images and processing errors remain visible for review.",
    )

    accepted = accepted_records(records)
    rejected = [row for row in records if row.get("status") == "rejected"]
    review = [row for row in records if row.get("status") == "review"]
    errors = [row for row in records if row.get("status") == "error"]
    total_lines = sum(len(row["result"].ocr_lines) for row in accepted)

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Accepted", len(accepted))
    c2.metric("Rejected", len(rejected))
    c3.metric("Needs review", len(review))
    c4.metric("Processing errors", len(errors))
    c5.metric("OCR lines", total_lines)

    for record in rejected:
        st.error(f"{record['filename']}: {SCREENSHOT_ERROR}")

        with st.expander(f"Rejected image · {record['filename']}"):
            st.image(
                record["preview_bytes"],
                use_container_width=True,
            )
            st.caption(record.get("validation_reason", ""))

            if record.get("raw_ocr_text"):
                st.text_area(
                    "Recognised text",
                    record["raw_ocr_text"],
                    height=130,
                    key=f"rejected_text_{safe_key(record['filename'])}",
                )


    for record in review:
        st.warning(f"{record['filename']}: {REVIEW_MESSAGE}")

        with st.expander(f"Review image · {record['filename']}"):
            st.image(
                record["preview_bytes"],
                use_container_width=True,
            )

            st.caption(record.get("validation_reason", ""))

            if record.get("validation_evidence"):
                st.write(
                    "Recognised indicators:",
                    ", ".join(record["validation_evidence"]),
                )

            st.text_area(
                "Recognised text",
                record.get("raw_ocr_text", ""),
                height=150,
                key=f"review_text_{safe_key(record['filename'])}",
            )

    for record in errors:
        with st.expander(f"Processing error · {record['filename']}", expanded=True):
            st.error(record.get("error", "Unknown processing error"))

    if accepted:
        subjects = sorted({row["subject_id"] for row in accepted})
        selection = st.selectbox(
            "Participant dashboard",
            ["All participants (separate sections)"] + subjects,
            help="Data from different subjects is never merged into one report.",
        )
        if selection == "All participants (separate sections)":
            for subject_id in subjects:
                render_subject_dashboard(records, subject_id)
                st.divider()
        else:
            render_subject_dashboard(records, selection)

    st.download_button(
        "Download complete JSON report",
        data=export_report(records),
        file_name="screenwise_full_report.json",
        mime="application/json",
        type="primary",
    )

st.divider()
st.caption(
    "ScreenWise · iPhone + Android screenshot recognition · "
    "Azure AI Vision OCR · participant separation · evidence retention"
)
