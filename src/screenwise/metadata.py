from __future__ import annotations

import re


def filename_metadata(filename: str) -> tuple[str | None, str | None]:
    """Extract BIDS-like subject/session IDs from a screenshot filename."""
    subject_match = re.search(r"(?:^|[_-])(sub-[A-Za-z0-9-]+)", filename, re.I)
    session_match = re.search(r"(?:^|[_-])(ses-[A-Za-z0-9-]+)", filename, re.I)
    return (
        subject_match.group(1) if subject_match else None,
        session_match.group(1) if session_match else None,
    )
