import re


def get_initial_fixtures() -> dict:
    """Return a fresh copy of initial state fixtures without shared references."""
    return {
        "calendar": [
            {
                "id": "meeting_1",
                "title": "Project Meeting",
                "time": "17:00",
                "date": "2026-10-15",
            }
        ],
        "reminders": [],
        "messages": [],
        "smart_home": {
            "living_room_light": {
                "id": "living_room_light",
                "name": "Living Room Light",
                "status": "off",
            },
            "kitchen_light": {
                "id": "kitchen_light",
                "name": "Kitchen Light",
                "status": "off",
            },
        },
        "shopping_list": [],
    }


STATE = get_initial_fixtures()


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
    """Restore the initial state before each test with fresh, unshared objects."""
    fixtures = get_initial_fixtures()
    STATE.clear()
    STATE.update(fixtures)


def send_message(recipient: str, message: str) -> dict:
    """Record a message in the simulated message log."""
    if not isinstance(recipient, str) or not recipient.strip():
        return {"success": False, "error": "Recipient is required"}

    if not isinstance(message, str) or not message.strip():
        return {"success": False, "error": "Message content is required"}

    sent_message = {
        "id": f"message_{len(STATE['messages']) + 1}",
        "recipient": recipient.strip(),
        "message": message.strip(),
    }

    STATE["messages"].append(sent_message)

    return {"success": True, "message": sent_message}


def set_device_state(
    device: str = "",
    status: str = None,
    *,
    device_id: str = None,
    state: str = None,
) -> dict:
    """Set a smart-home device (e.g. light) to on or off."""
    dev = (device or device_id or "").strip()
    target = (status or state or "").strip().lower()

    if not dev:
        return {"success": False, "error": "Device is required"}

    if target not in ["on", "off"]:
        return {"success": False, "error": "Status must be 'on' or 'off'"}

    dev_key = dev.lower().replace(" ", "_")

    target_key = None
    if dev_key in STATE.get("smart_home", {}):
        target_key = dev_key
    elif dev in STATE.get("smart_home", {}):
        target_key = dev
    else:
        for k, v in STATE.get("smart_home", {}).items():
            if isinstance(v, dict):
                if v.get("id") == dev_key or v.get("name", "").lower() == dev.lower():
                    target_key = k
                    break
            elif k == dev_key:
                target_key = k
                break

    if not target_key:
        return {"success": False, "error": f"Device '{dev}' not found"}

    device_entry = STATE["smart_home"][target_key]
    if isinstance(device_entry, dict):
        device_entry["status"] = target
    else:
        STATE["smart_home"][target_key] = target

    return {
        "success": True,
        "message": f"{target_key} turned {target}",
        "device": target_key,
        "status": target,
        "state": target,
    }


def add_shopping_item(item: str) -> dict:
    """Add an item to the shopping list."""
    if not isinstance(item, str) or not item.strip():
        return {"success": False, "error": "Item name is required"}

    cleaned_item = item.strip()
    if "shopping_list" not in STATE:
        STATE["shopping_list"] = []
    STATE["shopping_list"].append(cleaned_item)

    items = list(STATE["shopping_list"])
    return {
        "success": True,
        "message": f"Added '{cleaned_item}' to shopping list",
        "item": cleaned_item,
        "shopping_list": items,
        "items": items,
    }


def get_shopping_list() -> dict:
    """View the current shopping list items."""
    items = list(STATE.get("shopping_list", []))
    return {
        "success": True,
        "shopping_list": items,
        "items": items,
    }
