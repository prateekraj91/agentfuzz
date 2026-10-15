from app.tools import (
    STATE,
    move_meeting,
    create_reminder,
    send_message,
    set_device_state,
    add_shopping_item,
    get_shopping_list,
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


# ── Smart home device tests ──────────────────────────────────────────


def test_set_device_state_turn_on_and_off():
    reset_state()

    # Turn living room light on
    res_on = set_device_state("living_room_light", "on")
    assert res_on["success"] is True
    assert res_on["device"] == "living_room_light"
    assert res_on["status"] == "on"
    assert STATE["smart_home"]["living_room_light"]["status"] == "on"

    # Turn living room light off
    res_off = set_device_state("living_room_light", "off")
    assert res_off["success"] is True
    assert res_off["status"] == "off"
    assert STATE["smart_home"]["living_room_light"]["status"] == "off"


def test_set_device_state_rejects_invalid_status():
    reset_state()
    result = set_device_state("living_room_light", "bright")

    assert result["success"] is False
    assert "Status must be 'on' or 'off'" in result["error"]


def test_set_device_state_rejects_missing_or_unknown_device():
    reset_state()

    res_empty = set_device_state("", "on")
    assert res_empty["success"] is False
    assert "Device is required" in res_empty["error"]

    res_unknown = set_device_state("unknown_gadget", "on")
    assert res_unknown["success"] is False
    assert "not found" in res_unknown["error"]


# ── Shopping list tests ──────────────────────────────────────────────


def test_add_shopping_item_and_get_list():
    reset_state()

    # Starts empty
    initial_list = get_shopping_list()
    assert initial_list["success"] is True
    assert initial_list["shopping_list"] == []

    # Add first item
    res1 = add_shopping_item("oat milk")
    assert res1["success"] is True
    assert res1["item"] == "oat milk"
    assert get_shopping_list()["shopping_list"] == ["oat milk"]

    # Add second item
    res2 = add_shopping_item("bananas")
    assert res2["success"] is True
    assert get_shopping_list()["shopping_list"] == ["oat milk", "bananas"]
    assert STATE["shopping_list"] == ["oat milk", "bananas"]


def test_add_shopping_item_rejects_empty():
    reset_state()

    res_empty = add_shopping_item("")
    assert res_empty["success"] is False
    assert "Item name is required" in res_empty["error"]

    res_spaces = add_shopping_item("   ")
    assert res_spaces["success"] is False


# ── Repeatable reset & no shared fixture mutation ────────────────────


def test_reset_state_restores_identical_fixtures_without_shared_mutation():
    reset_state()

    # Mutate all sections of STATE
    move_meeting("meeting_1", "19:00")
    create_reminder("Dentist", "14:00")
    send_message("Alice", "Hello")
    set_device_state("living_room_light", "on")
    add_shopping_item("coffee")

    # Verify mutations took effect
    assert STATE["calendar"][0]["time"] == "19:00"
    assert len(STATE["reminders"]) == 1
    assert len(STATE["messages"]) == 1
    assert STATE["smart_home"]["living_room_light"]["status"] == "on"
    assert STATE["shopping_list"] == ["coffee"]

    # Reset
    reset_state()

    # Verify fresh initial fixtures
    assert STATE["calendar"][0]["time"] == "17:00"
    assert STATE["calendar"][0]["title"] == "Project Meeting"
    assert STATE["reminders"] == []
    assert STATE["messages"] == []
    assert STATE["smart_home"]["living_room_light"]["status"] == "off"
    assert STATE["smart_home"]["kitchen_light"]["status"] == "off"
    assert STATE["shopping_list"] == []

    # Direct in-place mutation to test that subsequent reset is clean
    STATE["calendar"][0]["title"] = "Mutated Title"
    STATE["shopping_list"].append("corrupted")
    STATE["smart_home"]["living_room_light"]["status"] = "broken"

    reset_state()

    assert STATE["calendar"][0]["title"] == "Project Meeting"
    assert STATE["shopping_list"] == []
    assert STATE["smart_home"]["living_room_light"]["status"] == "off"