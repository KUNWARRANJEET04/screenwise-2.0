from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from screenwise.config import settings
from screenwise.extraction.pipeline import process_screenshot
from screenwise.extraction.screen_time_parser import (
    is_screen_time_ocr,
    parse_screen_time_text,
)
from screenwise.ingestion.screenshot_ingestor import ingest_image
from screenwise.metadata import filename_metadata
from screenwise.schemas.common import ExtractionStatus, ValidationStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("screenwise.ui")

st.set_page_config(
    page_title="ScreenWise | Usage Intelligence",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {max-width:1480px;padding-top:1.5rem;padding-bottom:3rem}
    [data-testid="stAppViewContainer"] {background:#0b1020}
    [data-testid="stSidebar"] {background:#11182b;border-right:1px solid #293653}
    [data-testid="stHeader"] {background:rgba(11,16,32,.88)}
    h1,h2,h3 {letter-spacing:-.035em}
    .sw-eyebrow {color:#a99fff;text-transform:uppercase;letter-spacing:.16em;
      font-size:.72rem;font-weight:800}
    .sw-subtitle {color:#a8b2c8;font-size:1rem;margin-top:-.4rem}
    .sw-card {background:linear-gradient(145deg,#151e34,#11182a);
      border:1px solid #293653;border-radius:16px;padding:17px 19px;min-height:112px}
    .sw-label {color:#9eabc4;font-size:.76rem;font-weight:700;
      text-transform:uppercase;letter-spacing:.08em}
    .sw-value {color:#f4f6ff;font-size:1.75rem;font-weight:800;margin-top:7px}
    .sw-note {color:#9eabc4;font-size:.78rem;margin-top:5px}
    .sw-pill {display:inline-block;border:1px solid #3a4665;color:#c9c4ff;
      background:#201d3e;border-radius:999px;padding:4px 10px;font-size:.75rem;font-weight:700}
    div[data-testid="stMetric"] {background:#151e34;border:1px solid #293653;
      border-radius:14px;padding:13px 15px}
    div[data-testid="stMetricLabel"] {color:#a8b2c8}
    div[data-testid="stMetricValue"] {color:#f4f6ff}
    .stButton>button[kind="primary"] {border:0;border-radius:10px;
      background:linear-gradient(90deg,#7567f8,#9a77ff);color:white;font-weight:800}
    [data-testid="stFileUploader"] {background:#121b30;border:1px dashed #58658a;
      border-radius:14px;padding:12px}
    hr {border-color:#293653}
    </style>
    """,
    unsafe_allow_html=True,
)

SCREENSHOT_ERROR = "Please upload a real iPhone Screen Time screenshot."

def fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"

def metric_card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f'<div class="sw-card"><div class="sw-label">{label}</div>'
        f'<div class="sw-value">{value}</div><div class="sw-note">{note}</div></div>',
        unsafe_allow_html=True,
    )

def model_to_dict(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()

def process_uploaded_files(
    files: list[Any],
    fallback_subject_id: str | None,
    fallback_session_id: str | None,
    study_label: str,
) -> list[dict]:
    records: list[dict] = []
    progress = st.progress(0, text="Preparing screenshots...")
    status = st.empty()

    for index, uploaded in enumerate(files):
        filename = Path(uploaded.name).name
        image_bytes = uploaded.getvalue()
        auto_subject, auto_session = filename_metadata(filename)
        subject_id = auto_subject or (fallback_subject_id.strip() if fallback_subject_id else None) or "subject-unassigned"
        session_id = auto_session or (fallback_session_id.strip() if fallback_session_id else None) or "session-unassigned"
        status.info(f"Processing {index + 1}/{len(files)} · {filename}")

        try:
            ingestion = ingest_image(image_bytes=image_bytes, original_filename=filename)
            extraction = process_screenshot(ingestion.screenshot)

            accepted, validation_evidence = is_screen_time_ocr(extraction.raw_ocr_text or "")
            if not accepted:
                records.append({
                    "filename": filename,
                    "subject_id": subject_id,
                    "session_id": session_id,
                    "status": "rejected",
                    "error": SCREENSHOT_ERROR,
                    "validation_evidence": validation_evidence,
                    "raw_ocr_text": extraction.raw_ocr_text or "",
                    "preview_bytes": image_bytes,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                })
                progress.progress((index + 1) / len(files), text=f"Checked {index + 1} of {len(files)}")
                continue

            extraction.metadata.subject_id = subject_id
            extraction.metadata.session_id = session_id
            parsed = parse_screen_time_text(extraction.raw_ocr_text or "")
            extraction.app_usage = parsed["app_usage"]
            extraction.category_usage = parsed["category_usage"]
            extraction.pickups = parsed["pickups"]

            # Keep category labels attached to each app using an explicit mapping.
            warnings = list(extraction.warnings)
            for warning in parsed["warnings"]:
                if warning not in warnings:
                    warnings.append(warning)
            extraction.warnings = warnings
            has_parsed_data = bool(
                extraction.app_usage or extraction.category_usage
                or extraction.pickups or parsed["total_screen_time_seconds"] is not None
            )
            extraction.extraction_status = (
                ExtractionStatus.COMPLETE if has_parsed_data and not warnings
                else ExtractionStatus.PARTIAL
            )
            extraction.validation_status = ValidationStatus.NEEDS_REVIEW

            records.append({
                "filename": filename,
                "subject_id": subject_id,
                "session_id": session_id,
                "study_label": study_label.strip(),
                "status": "accepted",
                "ingestion_status": ingestion.status.value,
                "ingestion_message": ingestion.message,
                "result": extraction,
                "parsed": parsed,
                "preview_bytes": image_bytes,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.exception("Failed to process %s", filename)
            records.append({
                "filename": filename,
                "subject_id": subject_id,
                "session_id": session_id,
                "status": "error",
                "error": str(exc),
                "preview_bytes": image_bytes,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            })

        progress.progress((index + 1) / len(files), text=f"Processed {index + 1} of {len(files)} screenshots")

    status.empty()
    progress.empty()
    return records

def successful_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "accepted" and r.get("result") is not None]

def records_for_subject(records: list[dict], subject_id: str) -> list[dict]:
    return [r for r in successful_records(records) if r["subject_id"] == subject_id]

def app_dataframe(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        for app in record["result"].app_usage:
            rows.append({
                "Subject": record["subject_id"],
                "Session": record["session_id"],
                "Screenshot": record["filename"],
                "App": app.app_name,
                "Category": app.category or "Unclassified",
                "Usage": fmt_duration(app.duration_seconds),
                "Minutes": round(app.duration_seconds / 60, 2),
            })
    return pd.DataFrame(rows)

def category_dataframe(records: list[dict]) -> pd.DataFrame:
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

def collect_subject_profiles(records: list[dict]) -> dict[str, dict]:
    profiles = {}
    for subject_id in sorted({r.get("subject_id") for r in successful_records(records)}):
        key = f"subject_profile_{re.sub(r'[^A-Za-z0-9_]', '_', subject_id)}"
        profiles[subject_id] = st.session_state.get(key, {"label": "", "cohort": "", "notes": ""})
    return profiles

def json_export(records: list[dict], profiles: dict[str, dict]) -> bytes:
    output = []
    for record in records:
        item = {
            "filename": record["filename"],
            "subject_id": record.get("subject_id"),
            "session_id": record.get("session_id"),
            "study_label": record.get("study_label", ""),
            "status": record.get("status"),
            "processed_at": record.get("processed_at"),
        }
        if record.get("result") is not None:
            item["extraction"] = model_to_dict(record["result"])
        else:
            item["error"] = record.get("error")
            item["validation_evidence"] = record.get("validation_evidence", [])
            item["raw_ocr_text"] = record.get("raw_ocr_text", "")
        output.append(item)
    return json.dumps({
        "application": "ScreenWise",
        "version": "2.1.0",
        "subject_profiles": profiles,
        "screenshots": output,
    }, indent=2, ensure_ascii=False).encode("utf-8")

def render_subject(records: list[dict], subject_id: str, study_label: str) -> None:
    subject_records = records_for_subject(records, subject_id)
    sessions = sorted({r["session_id"] for r in subject_records})
    profile_key = f"subject_profile_{re.sub(r'[^A-Za-z0-9_]', '_', subject_id)}"
    profile = st.session_state.setdefault(profile_key, {"label": "", "cohort": "", "notes": ""})

    st.markdown(f"## Participant · `{subject_id}`")
    p1, p2, p3 = st.columns(3)
    with p1:
        metric_card("Screenshots", str(len(subject_records)), "Accepted Screen Time screenshots")
    with p2:
        metric_card("Sessions", str(len(sessions)), ", ".join(sessions) if sessions else "No session ID")
    with p3:
        pickups = [r["result"].pickups.total_pickups for r in subject_records if r["result"].pickups]
        metric_card("Pickups (reported)", f"{max(pickups):,}" if pickups else "—", "Highest displayed value; screenshots are not added together")

    with st.expander("Participant information", expanded=True):
        a, b = st.columns(2)
        with a:
            profile["label"] = st.text_input("Participant label (optional)", value=profile["label"], key=f"{profile_key}_label")
            profile["cohort"] = st.text_input("Cohort / group (optional)", value=profile["cohort"], key=f"{profile_key}_cohort")
        with b:
            profile["notes"] = st.text_area("Participant notes (optional)", value=profile["notes"], key=f"{profile_key}_notes", height=90)
        st.caption(f"Study/project: {study_label or 'Not specified'}")

    selected_session = st.selectbox(
        f"Session view · {subject_id}",
        ["All sessions"] + sessions,
        key=f"session_filter_{profile_key}",
    )
    view_records = subject_records if selected_session == "All sessions" else [r for r in subject_records if r["session_id"] == selected_session]

    apps = app_dataframe(view_records)
    cats = category_dataframe(view_records)
    st.markdown("### App usage with categories")
    if apps.empty:
        st.info("No app-level usage was extracted for this participant/session.")
    else:
        st.dataframe(apps.drop(columns=["Minutes"]), use_container_width=True, hide_index=True)
        st.bar_chart(apps.groupby("App", as_index=True)["Minutes"].max().sort_values(ascending=False), height=260)
        st.download_button(
            f"Download {subject_id} app CSV",
            apps.to_csv(index=False).encode("utf-8"),
            file_name=f"{subject_id}_app_usage.csv",
            mime="text/csv",
            key=f"csv_apps_{profile_key}",
        )

    st.markdown("### iPhone category usage")
    if cats.empty:
        st.info("No category-duration panel was identified in these screenshots.")
    else:
        st.dataframe(cats.drop(columns=["Minutes"]), use_container_width=True, hide_index=True)
        st.bar_chart(cats.groupby("Category", as_index=True)["Minutes"].max().sort_values(ascending=False), height=220)
        st.download_button(
            f"Download {subject_id} category CSV",
            cats.to_csv(index=False).encode("utf-8"),
            file_name=f"{subject_id}_category_usage.csv",
            mime="text/csv",
            key=f"csv_cats_{profile_key}",
        )

    st.markdown("### Screenshot records")
    for index, record in enumerate(view_records):
        result = record["result"]
        with st.expander(f"📄 {record['filename']} · {record['session_id']} · {result.extraction_status.value.upper()}", expanded=False):
            st.caption(f"Original file: {record['filename']} · Ingestion: {record.get('ingestion_status', 'unknown')}")
            st.image(record["preview_bytes"], caption="Uploaded screenshot", use_container_width=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Total screen time", fmt_duration(record["parsed"].get("total_screen_time_seconds")))
            m2.metric("Displayed average", fmt_duration(record["parsed"].get("average_seconds")))
            m3.metric("Pickups", str(result.pickups.total_pickups) if result.pickups else "—")
            if result.confidence is not None:
                st.progress(float(result.confidence), text=f"Azure OCR confidence · {result.confidence:.1%}")
            if result.warnings:
                for warning in result.warnings:
                    st.warning(warning)
            tab1, tab2 = st.tabs(["Recognised OCR text", "Structured JSON"])
            with tab1:
                st.text_area("OCR text", result.raw_ocr_text or "", height=220, key=f"ocr_{profile_key}_{index}")
                if result.evidence:
                    evidence = [{
                        "Text": e.raw_text,
                        "Field": e.field_path,
                        "Bounding box": str(e.bounding_box) if e.bounding_box else "—",
                    } for e in result.evidence]
                    st.dataframe(pd.DataFrame(evidence), use_container_width=True, hide_index=True)
            with tab2:
                st.json(model_to_dict(result))

# Sidebar settings and provider readiness
with st.sidebar:
    st.markdown("## 📱 ScreenWise")
    st.caption("iPhone Usage Intelligence · 2.1")
    st.divider()
    st.markdown("### Study information")
    study_label = st.text_input("Study / project name", placeholder="e.g. Screen Time Study")
    fallback_subject_id = st.text_input("Default subject ID", placeholder="Used only when filename has no sub-XXXXX")
    fallback_session_id = st.text_input("Default session ID", placeholder="Used only when filename has no ses-XX")
    st.caption("Filenames containing sub-XXXXX and ses-XX are identified automatically.")
    st.divider()
    if settings.azure_vision_endpoint and settings.azure_vision_key:
        st.success("Azure Vision configured")
    else:
        st.error("Azure Vision configuration missing")
        st.caption("Set AZURE_VISION_ENDPOINT and AZURE_VISION_KEY in .env.")

st.markdown('<div class="sw-eyebrow">SCREEN TIME ANALYTICS</div>', unsafe_allow_html=True)
st.title("Understand your screen time.")
st.markdown('<div class="sw-subtitle">Turn iPhone Screen Time screenshots into structured, auditable usage insights.</div>', unsafe_allow_html=True)

left, right = st.columns([2.3, 1])
with left:
    st.markdown("### Upload screenshots")
    st.caption("Upload up to five images per batch. Different participants are supported and automatically separated.")
with right:
    st.markdown('<div style="text-align:right;padding-top:12px"><span class="sw-pill">MICROSOFT AZURE AI VISION</span></div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Choose iPhone Screen Time screenshots",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    help="Use original screenshots. Maximum five files per batch.",
)

if uploaded_files:
    if len(uploaded_files) > 5:
        st.error("Please upload no more than five screenshots in one batch.")
    else:
        for i, uploaded in enumerate(uploaded_files):
            with st.expander(f"Preview · {uploaded.name}", expanded=False):
                st.image(uploaded.getvalue(), caption=uploaded.name, use_container_width=True)

can_process = bool(uploaded_files) and len(uploaded_files) <= 5 and bool(settings.azure_vision_endpoint and settings.azure_vision_key)
if st.button("Analyse screenshots", type="primary", use_container_width=True, disabled=not can_process):
    with st.spinner("Validating screenshots and extracting usage information..."):
        st.session_state["screenwise_records"] = process_uploaded_files(
            uploaded_files,
            fallback_subject_id,
            fallback_session_id,
            study_label,
        )
        st.session_state["screenwise_study_label"] = study_label

records = st.session_state.get("screenwise_records", [])
if records:
    st.divider()
    accepted = successful_records(records)
    rejected = [r for r in records if r.get("status") == "rejected"]
    errors = [r for r in records if r.get("status") == "error"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accepted screenshots", len(accepted))
    c2.metric("Rejected images", len(rejected))
    c3.metric("Processing errors", len(errors))
    c4.metric("OCR lines", sum(len(r["result"].ocr_lines) for r in accepted))

    for record in rejected:
        st.error(f"{record['filename']}: {SCREENSHOT_ERROR}")
        if record.get("validation_evidence"):
            st.caption("OCR indicators found: " + ", ".join(record["validation_evidence"]))
        with st.expander(f"Review rejected image · {record['filename']}"):
            st.image(record["preview_bytes"], use_container_width=True)
            if record.get("raw_ocr_text"):
                st.text_area("Recognised text", record["raw_ocr_text"], height=120, key=f"rejected_{record['filename']}")
    for record in errors:
        st.error(f"{record['filename']}: {record.get('error', 'Unknown processing error')}")

    if accepted:
        subjects = sorted({r["subject_id"] for r in accepted})
        selection = st.selectbox(
            "Participant dashboard",
            ["All participants (separate sections)"] + subjects,
            help="Each participant is rendered separately. Usage from different subjects is never combined.",
        )
        if selection == "All participants (separate sections)":
            for subject in subjects:
                render_subject(accepted, subject, st.session_state.get("screenwise_study_label", ""))
                st.divider()
        else:
            render_subject(accepted, selection, st.session_state.get("screenwise_study_label", ""))

    st.download_button(
        "Download complete JSON report",
        data=json_export(records, collect_subject_profiles(records)),
        file_name="screenwise_full_report.json",
        mime="application/json",
        type="primary",
    )
    if st.button("Clear analysis results"):
        st.session_state.pop("screenwise_records", None)
        st.rerun()
else:
    st.info("Upload your iPhone Screen Time screenshots and select Analyse screenshots to begin.")

st.divider()
st.caption("ScreenWise 2.1 · Azure OCR · deterministic parsing · subject/session separation · evidence retention.")
