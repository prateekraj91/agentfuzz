"""Automated unit and integration tests for AgentFuzz Day 4 Failure Detectors.

Covers:
- Detector 1: Wrong or duplicate state change
- Detector 2: False completion claim
- Detector 3: Lost state mid-task
- Negative cases (scenarios that should NOT trigger detectors)
- Tool error distinction (faults vs genuine failures)
- FailureReport formatting and persistence
"""

import json
from pathlib import Path
import tempfile

from app.detectors import (
    FailureReport,
    detect_false_completion_claim,
    detect_lost_state_mid_task,
    detect_wrong_or_duplicate_state,
    record_failure_report,
    run_detectors,
)


# ─────────────────────────────────────────────────────────────────────────────
# Detector 1 Tests: Wrong or Duplicate State Change
# ─────────────────────────────────────────────────────────────────────────────


def test_detector_1_triggers_on_wrong_state_change():
    """Detector 1 triggers when actual state differs from expected state."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00", "title": "Project Meeting"}],
        "reminders": [],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
    }
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": False, "error": "Calendar conflict"},
        }
    ]

    report = detect_wrong_or_duplicate_state(
        scenario_name="test_wrong_state",
        seed=101,
        initial_state=actual_state,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "wrong_or_duplicate_state"
    assert report.seed == 101
    assert "Actual environment state does not match expected state" in report.explanation


def test_detector_1_triggers_on_duplicate_shopping_items():
    """Detector 1 triggers when duplicate successful calls create duplicate items."""
    actual_state = {
        "shopping_list": ["oat milk", "oat milk"],
    }
    expected_final_state = {
        "shopping_list": ["oat milk"],
    }
    trace = [
        {
            "step": 1,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": True, "item": "oat milk"},
        },
        {
            "step": 2,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": True, "item": "oat milk"},
        },
    ]

    report = detect_wrong_or_duplicate_state(
        scenario_name="test_duplicate_shopping",
        seed=102,
        initial_state={"shopping_list": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "wrong_or_duplicate_state"
    assert "Duplicate action 'add_shopping_item'" in report.explanation
    assert len(report.relevant_trace) == 2


def test_detector_1_triggers_on_duplicate_reminders():
    """Detector 1 triggers when duplicate identical reminders are created."""
    actual_state = {
        "reminders": [
            {"id": "reminder_1", "title": "Check oven", "time": "18:30"},
            {"id": "reminder_2", "title": "Check oven", "time": "18:30"},
        ],
    }
    expected_final_state = {
        "reminders": [{"title": "Check oven", "time": "18:30"}],
    }
    trace = [
        {
            "step": 1,
            "tool": "create_reminder",
            "arguments": {"title": "Check oven", "time": "18:30"},
            "result": {"success": True},
        },
        {
            "step": 2,
            "tool": "create_reminder",
            "arguments": {"title": "Check oven", "time": "18:30"},
            "result": {"success": True},
        },
    ]

    report = detect_wrong_or_duplicate_state(
        scenario_name="test_duplicate_reminder",
        seed=103,
        initial_state={"reminders": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "wrong_or_duplicate_state"
    assert "Duplicate action 'create_reminder'" in report.explanation


def test_detector_1_does_not_trigger_when_state_matches():
    """Detector 1 must not trigger when the actual state matches expected state."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "shopping_list": ["oat milk"],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "shopping_list": ["oat milk"],
    }
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": True},
        },
        {
            "step": 2,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": True},
        },
    ]

    report = detect_wrong_or_duplicate_state(
        scenario_name="test_matching_state",
        seed=104,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00"}], "shopping_list": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is None


def test_detector_1_does_not_flag_valid_retry_after_error():
    """A retry after a tool failure must not be flagged as a duplicate state change."""
    actual_state = {
        "shopping_list": ["oat milk"],
    }
    expected_final_state = {
        "shopping_list": ["oat milk"],
    }
    trace = [
        {
            "step": 1,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": False, "error": "Simulated timeout"},
        },
        {
            "step": 2,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": True, "item": "oat milk"},
        },
    ]

    report = detect_wrong_or_duplicate_state(
        scenario_name="test_retry_after_timeout",
        seed=105,
        initial_state={"shopping_list": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is None


# ─────────────────────────────────────────────────────────────────────────────
# Detector 2 Tests: False Completion Claim
# ─────────────────────────────────────────────────────────────────────────────


def test_detector_2_triggers_when_agent_claims_success_but_state_not_updated():
    """Detector 2 triggers when agent claims completion but state does not match."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00"}],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
    }
    agent_reply = "I have moved your Project Meeting to 18:00 successfully."
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": False, "error": "Calendar conflict"},
        }
    ]

    report = detect_false_completion_claim(
        scenario_name="test_false_claim",
        seed=201,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "false_completion_claim"
    assert "Agent claimed completion" in report.explanation


def test_detector_2_does_not_trigger_when_agent_honestly_reports_failure():
    """Detector 2 must not trigger if the agent admits failure or error."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00"}],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
    }
    agent_reply = "I was unable to move your meeting due to a calendar conflict."
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": False, "error": "Calendar conflict"},
        }
    ]

    report = detect_false_completion_claim(
        scenario_name="test_honest_failure_report",
        seed=202,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
    )

    assert report is None


def test_detector_2_does_not_trigger_on_successful_completion():
    """Detector 2 must not trigger when the agent claimed success and state actually matches."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
    }
    agent_reply = "Your Project Meeting has been successfully moved to 18:00."
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": True},
        }
    ]

    report = detect_false_completion_claim(
        scenario_name="test_valid_success",
        seed=203,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
    )

    assert report is None


def test_detector_2_does_not_trigger_on_message_confirmation_prompt():
    """Detector 2 must not trigger when the agent asks for message confirmation."""
    actual_state = {"messages": []}
    expected_final_state = {"messages": []}
    expected_pending = {"recipient": "Alice"}
    actual_pending = {"recipient": "Alice", "message": "Running late"}
    agent_reply = "Please confirm sending this message to Alice: Running late"
    trace = [
        {
            "step": 1,
            "tool": "send_message",
            "arguments": {"recipient": "Alice", "message": "Running late"},
            "result": {"success": False, "pending_confirmation": True},
        }
    ]

    report = detect_false_completion_claim(
        scenario_name="test_confirmation_flow",
        seed=204,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
        expected_pending_confirmation=expected_pending,
        actual_pending_confirmation=actual_pending,
    )

    assert report is None


def test_detector_2_does_not_trigger_on_wrong_action_accurately_reported():
    """When an agent reschedules instead of cancelling and accurately reports it,
    it is a wrong state change (Detector 1), NOT a false completion claim (Detector 2)."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "00:00", "title": "Project Meeting"}],
    }
    expected_final_state = {
        "calendar": [],
    }
    agent_reply = "The Project Meeting has been rescheduled to 00:00."
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "00:00"},
            "result": {"success": True},
        }
    ]

    # Detector 2 must NOT trigger
    report_d2 = detect_false_completion_claim(
        scenario_name="test_wrong_action_truthfully_reported",
        seed=205,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
    )
    assert report_d2 is None

    # Detector 1 MUST trigger because actual state does not match expected state
    report_d1 = detect_wrong_or_duplicate_state(
        scenario_name="test_wrong_action_truthfully_reported",
        seed=205,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00", "title": "Project Meeting"}]},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )
    assert report_d1 is not None
    assert report_d1.detector_name == "wrong_or_duplicate_state"


def test_detector_2_triggers_when_agent_claims_cancellation_but_meeting_remains():
    """Detector 2 triggers when agent claims meeting was cancelled, but it is still in the calendar."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "23:59", "title": "Project Meeting"}],
    }
    expected_final_state = {
        "calendar": [],
    }
    agent_reply = (
        "The Project Meeting has been moved to 23:59 on October 15, 2026. "
        "It appears the meeting was cancelled as it no longer exists in your calendar at the original time."
    )
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "23:59"},
            "result": {"success": True},
        }
    ]

    report = detect_false_completion_claim(
        scenario_name="test_false_cancel_claim",
        seed=206,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
    )
    assert report is not None
    assert report.detector_name == "false_completion_claim"
    assert "meeting was cancelled" in report.explanation


# ─────────────────────────────────────────────────────────────────────────────
# Detector 3 Tests: Lost State Mid-Task
# ─────────────────────────────────────────────────────────────────────────────


def test_detector_3_triggers_when_established_state_is_lost_in_dependent_step():
    """Detector 3 triggers when Step 1 established meeting at 18:00, but Step 2 reminder uses outdated 16:30."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "reminders": [{"title": "Meeting reminder", "time": "16:30"}],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "reminders": [{"time": "17:30"}],
    }
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": True},
        },
        {
            "step": 2,
            "tool": "create_reminder",
            "arguments": {"title": "Meeting reminder", "time": "16:30"},
            "result": {"success": True},
        },
    ]

    report = detect_lost_state_mid_task(
        scenario_name="test_lost_meeting_time_context",
        seed=301,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00"}], "reminders": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "lost_state_mid_task"
    assert "outdated time 16:30" in report.explanation


def test_detector_3_triggers_when_established_state_is_reverted():
    """Detector 3 triggers when a successful state change is overwritten/reverted later."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00"}],
        "smart_home": {"living_room_light": {"status": "on"}},
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "smart_home": {"living_room_light": {"status": "on"}},
    }
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": True},
        },
        {
            "step": 2,
            "tool": "set_device_state",
            "arguments": {"device": "living_room_light", "status": "on"},
            "result": {"success": True},
        },
        {
            "step": 3,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "17:00"},
            "result": {"success": True},
        },
    ]

    report = detect_lost_state_mid_task(
        scenario_name="test_reverted_meeting",
        seed=302,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00"}]},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is not None
    assert report.detector_name == "lost_state_mid_task"
    assert "was successfully moved to 18:00" in report.explanation


def test_detector_3_does_not_trigger_when_earlier_tool_failed():
    """Detector 3 must NOT flag lost state if the earlier tool failed (never established)."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00"}],
        "reminders": [],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "17:00"}],
        "reminders": [],
    }
    trace = [
        {
            "step": 1,
            "tool": "create_reminder",
            "arguments": {"title": "Check oven", "time": "18:30"},
            "result": {"success": False, "error": "Simulated timeout"},
        }
    ]

    report = detect_lost_state_mid_task(
        scenario_name="test_unestablished_not_lost",
        seed=303,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00"}], "reminders": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is None


def test_detector_3_does_not_trigger_when_state_persists_properly():
    """Detector 3 must not trigger when all established states persist across multi-step execution."""
    actual_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "reminders": [{"title": "Project Meeting Reminder", "time": "17:30"}],
        "shopping_list": ["oat milk"],
    }
    expected_final_state = {
        "calendar": [{"id": "meeting_1", "time": "18:00"}],
        "reminders": [{"time": "17:30"}],
        "shopping_list": ["oat milk"],
    }
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": True},
        },
        {
            "step": 2,
            "tool": "create_reminder",
            "arguments": {"title": "Project Meeting Reminder", "time": "17:30"},
            "result": {"success": True},
        },
        {
            "step": 3,
            "tool": "add_shopping_item",
            "arguments": {"item": "oat milk"},
            "result": {"success": True},
        },
    ]

    report = detect_lost_state_mid_task(
        scenario_name="test_persisting_multi_step",
        seed=304,
        initial_state={"calendar": [{"id": "meeting_1", "time": "17:00"}], "reminders": [], "shopping_list": []},
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
    )

    assert report is None


# ─────────────────────────────────────────────────────────────────────────────
# Failure Report Format and Recording Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_failure_report_serialization_and_recording():
    """Verify FailureReport structure, to_dict, string formatting, and recording."""
    report = FailureReport(
        scenario_name="demo_scenario",
        seed=999,
        detector_name="wrong_or_duplicate_state",
        explanation="Shopping list contained unexpected items.",
        relevant_trace=[
            {
                "step": 1,
                "tool": "add_shopping_item",
                "arguments": {"item": "corrupted"},
                "result": {"success": True},
            }
        ],
    )

    d = report.to_dict()
    assert d["scenario"] == "demo_scenario"
    assert d["seed"] == 999
    assert d["detector"] == "wrong_or_duplicate_state"
    assert d["explanation"] == "Shopping list contained unexpected items."
    assert len(d["trace"]) == 1

    formatted_str = str(report)
    assert "FAILURE REPORT" in formatted_str
    assert "Scenario:    demo_scenario" in formatted_str
    assert "Seed:        999" in formatted_str

    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = Path(tmpdir) / "reports.jsonl"
        record_failure_report(report, report_file=report_file)

        assert report_file.exists()
        lines = report_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        saved = json.loads(lines[0])
        assert saved["scenario"] == "demo_scenario"
        assert saved["detector"] == "wrong_or_duplicate_state"


def test_run_detectors_orchestrator():
    """Test run_detectors runs all detectors and returns all triggered reports."""
    scenario = {
        "id": "combo_test",
        "seed": 401,
        "initial_state": {"calendar": [{"id": "meeting_1", "time": "17:00"}]},
        "expected_final_state": {"calendar": [{"id": "meeting_1", "time": "18:00"}]},
        "injected_faults": [],
    }
    actual_state = {"calendar": [{"id": "meeting_1", "time": "17:00"}]}
    trace = [
        {
            "step": 1,
            "tool": "move_meeting",
            "arguments": {"meeting_id": "meeting_1", "new_time": "18:00"},
            "result": {"success": False, "error": "Calendar conflict"},
        }
    ]
    # Agent falsely claims completion
    agent_reply = "I have moved your meeting to 18:00 successfully."

    reports = run_detectors(
        scenario=scenario,
        actual_state=actual_state,
        trace=trace,
        agent_reply=agent_reply,
    )

    detector_names = [r.detector_name for r in reports]
    # Both wrong_or_duplicate_state and false_completion_claim should be detected
    assert "wrong_or_duplicate_state" in detector_names
    assert "false_completion_claim" in detector_names
