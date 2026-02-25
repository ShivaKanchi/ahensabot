import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

# Mock loguru only during import to avoid side effects on other tests
with patch.dict(sys.modules, {"loguru": MagicMock()}):
    from nanobot.cron.service import _compute_next_run
    from nanobot.cron.types import CronSchedule

def test_compute_next_run_at_future():
    now = 1000
    schedule = CronSchedule(kind="at", at_ms=2000)
    assert _compute_next_run(schedule, now) == 2000

def test_compute_next_run_at_past():
    now = 1000
    schedule = CronSchedule(kind="at", at_ms=500)
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_at_missing():
    now = 1000
    schedule = CronSchedule(kind="at", at_ms=None)
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_every_positive():
    now = 1000
    schedule = CronSchedule(kind="every", every_ms=500)
    assert _compute_next_run(schedule, now) == 1500

def test_compute_next_run_every_zero():
    now = 1000
    schedule = CronSchedule(kind="every", every_ms=0)
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_every_negative():
    now = 1000
    schedule = CronSchedule(kind="every", every_ms=-100)
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_every_missing():
    now = 1000
    schedule = CronSchedule(kind="every", every_ms=None)
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_unknown_kind():
    now = 1000
    schedule = CronSchedule(kind="unknown") # type: ignore
    assert _compute_next_run(schedule, now) is None

def test_compute_next_run_cron_success():
    now = 1000000 # 1000s
    schedule = CronSchedule(kind="cron", expr="* * * * *")

    mock_croniter_class = MagicMock()
    mock_cron = MagicMock()
    mock_croniter_class.return_value = mock_cron

    # Use explicit UTC timezone for robustness
    mock_next_dt = datetime.fromtimestamp(1001, tz=timezone.utc)
    mock_cron.get_next.return_value = mock_next_dt

    mock_croniter_module = MagicMock()
    mock_croniter_module.croniter = mock_croniter_class

    with patch.dict(sys.modules, {"croniter": mock_croniter_module}):
        result = _compute_next_run(schedule, now)

    assert result == 1001000
    mock_croniter_class.assert_called_once()

def test_compute_next_run_cron_missing_croniter():
    now = 1000
    schedule = CronSchedule(kind="cron", expr="* * * * *")

    # Simulate missing croniter by making import fail
    with patch.dict(sys.modules, {"croniter": None}):
        result = _compute_next_run(schedule, now)
        assert result is None

def test_compute_next_run_cron_invalid_expr():
    now = 1000
    schedule = CronSchedule(kind="cron", expr="invalid")

    mock_croniter_class = MagicMock(side_effect=Exception("Invalid cron"))
    mock_croniter_module = MagicMock()
    mock_croniter_module.croniter = mock_croniter_class

    with patch.dict(sys.modules, {"croniter": mock_croniter_module}):
        result = _compute_next_run(schedule, now)
        assert result is None
