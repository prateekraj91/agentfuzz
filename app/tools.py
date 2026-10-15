import re


STATE = {
    "calendar": [
        {
            "id": "meeting_1",
            "title": "Project Meeting",
            "time": "17:00",
            "date": "2026-10-15",
        }
    ],
    "reminders": [],
}

def is_valid_time(value: str) -> bool:
    """Check whether a time is in 24-hour HH:MM format."""
    if not isinstance(value, str):
        return False

    if not re.fullmatch(r"\d{2}:\d{2}", value):
        return False

    hours, minutes = map(int, value.split(":"))
    return 0 <= hours <= 23 and 0 <= minutes <= 59


def move_meeting(
    meeting_id: str,
    new_time: str,
) -> dict:
    """Move an existing meeting to a new time."""
    if not isinstance(meeting_id, str) or not meeting_id.strip():
        return {"success": False, "error": "Meeting ID is required"}
    if not is_valid_time(new_time):
        return {"success": False, "error": "Invalid time; use HH:MM"}

    meeting = next(
        (m for m in STATE["calendar"] if m["id"] == meeting_id),
        None,
    )

    if meeting is None:
        return {"success": False, "error": "Meeting not found"}

    meeting["time"] = new_time

    return {
        "success": True,
        "message": f"{meeting['title']} moved to {new_time}",
        "calendar": STATE["calendar"],
    }


def create_reminder(
    title: str,
    time: str,
) -> dict:
    """Create a reminder at a specified time."""
    if not isinstance(title, str) or not title.strip():
        return {"success": False, "error": "Reminder title is required"}
    if not is_valid_time(time):
        return {"success": False, "error": "Invalid time; use HH:MM"}

    reminder = {
        "id": f"reminder_{len(STATE['reminders']) + 1}",
        "title": title,
        "time": time,
    }

    STATE["reminders"].append(reminder)

    return {"success": True, "reminder": reminder}

def reset_state():
    """Restore the initial state before each test."""
    STATE["calendar"] = [
        {
            "id": "meeting_1",
            "title": "Project Meeting",
            "time": "17:00",
            "date": "2026-10-15",
        }
    ]
    STATE["reminders"] = []
