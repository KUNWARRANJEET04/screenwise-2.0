
from screenwise.health import run_health_check


def test_health_check():
    result = run_health_check()

    assert result["application"] == "ScreenWise"
    assert result["version"] == "2.0.0"
    assert result["status"] == "healthy"


def test_required_directories_exist():
    result = run_health_check()

    assert result["data_directory"] is True
    assert result["upload_directory"] is True
    assert result["processed_directory"] is True
