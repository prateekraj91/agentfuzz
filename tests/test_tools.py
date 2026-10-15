from app.tools import (
    STATE,
    move_meeting,
    create_reminder,
    reset_state,
)


def test_move_meeting_success():
    reset_state()
    result = move_meeting("meeting_1", "18:00")

    assert result["success"] is True
    assert STATE["calendar"][0]["time"] == "18:00"


def test_move_meeting_rejects_invalid_time():
    reset_state()
    result = move_meeting("meeting_1", "25:90")

    assert result["success"] is False
    assert STATE["calendar"][0]["time"] == "17:00"


def test_create_reminder_rejects_invalid_time():
    reset_state()
    result = create_reminder("Test reminder", "banana")

    assert result["success"] is False
    assert STATE["reminders"] == []