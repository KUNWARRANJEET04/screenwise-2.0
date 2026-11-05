from screenwise.metadata import filename_metadata


def test_extract_subject_and_session_from_bids_filename():
    assert filename_metadata("sub-00132_ses-01_task-screentime_run-05_screenshot.jpg") == ("sub-00132", "ses-01")


def test_filename_without_metadata_returns_none():
    assert filename_metadata("screen-time.png") == (None, None)
