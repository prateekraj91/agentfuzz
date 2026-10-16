"""CLI runner for AgentFuzz JSON scenarios."""

import copy
import json
from pathlib import Path
import sys

from app.agent import run_agent
from app.detectors import FailureReport, record_failure_report, run_detectors, subset_match
from app.faults import clear_faults, set_faults
from app.pending import clear_pending_message, get_pending_message
from app.tools import STATE, reset_state


def validate_scenario(data: dict) -> tuple[bool, str]:
    """Validate that required fields exist and have correct types."""
    required_fields = [
        "id",
        "seed",
        "initial_state",
        "user_request",
        "injected_faults",
        "expected_final_state",
    ]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: '{field}'"

    if not isinstance(data["seed"], int):
        return False, "Field 'seed' must be an integer"

    if not isinstance(data["initial_state"], dict):
        return False, "Field 'initial_state' must be a dictionary"

    if not isinstance(data["user_request"], str) or not data["user_request"].strip():
        return False, "Field 'user_request' must be a non-empty string"

    if not isinstance(data["injected_faults"], list):
        return False, "Field 'injected_faults' must be a list"

    if not isinstance(data["expected_final_state"], dict):
        return False, "Field 'expected_final_state' must be a dictionary"

    return True, ""


def check_subset_match(actual: any, expected: any, path: str = "") -> tuple[bool, str]:
    """Check that actual matches all declared properties in expected."""
    return subset_match(actual, expected, path)


def check_fault_triggered(trace: list[dict], expected_fault: dict) -> tuple[bool, str]:
    """Verify that expected fault was triggered during the agent run."""
    target_tool = expected_fault.get("tool")
    target_type = expected_fault.get("type")

    for step in trace:
        tool_name = step.get("tool")
        result = step.get("result", {})
        fault_info = result.get("fault", {})

        if target_tool and tool_name != target_tool:
            continue

        if result.get("success") is False:
            if target_type and fault_info.get("type") == target_type:
                return True, ""

    return False, f"Expected fault {expected_fault} was not triggered in trace"


def run_scenario(scenario_path: Path) -> tuple[str, str, list[FailureReport]]:
    """Execute a single scenario file and verify its outcome.

    Returns:
        status: 'PASS', 'FAIL', or 'DETECTED'
        message: Explanation string
        reports: List of FailureReport objects produced by detectors
    """
    try:
        with scenario_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return "FAIL", f"Failed to load JSON: {exc}", []

    valid, reason = validate_scenario(data)
    if not valid:
        return "FAIL", f"Validation error: {reason}", []

    # Reset state to declared initial state
    STATE.clear()
    STATE.update(copy.deepcopy(data["initial_state"]))
    clear_pending_message()
    set_faults(data.get("injected_faults", []))

    try:
        options = data.get("options")
        result = run_agent(data["user_request"], options=options)
        actual_state = copy.deepcopy(STATE)
        actual_pending = copy.deepcopy(get_pending_message())
        trace = result.get("trace", [])
        reply = result.get("reply", "")

        # Run all three failure detectors
        reports = run_detectors(
            scenario=data,
            actual_state=actual_state,
            trace=trace,
            agent_reply=reply,
            actual_pending=actual_pending,
        )

        for report in reports:
            record_failure_report(report)

        expected_detector = data.get("expected_detector")

        # Case 1: Scenario specifically expects a failure detector to trigger
        if expected_detector:
            matching = [r for r in reports if r.detector_name == expected_detector]
            if matching:
                return "DETECTED", f"Caught expected failure via detector '{expected_detector}': {matching[0].explanation}", reports
            return "FAIL", f"Expected detector '{expected_detector}' did not trigger. Reports: {[r.detector_name for r in reports]}", reports

        # Case 2: Standard scenario (no expected failure detector)
        if reports:
            first = reports[0]
            return "FAIL", f"Detector '{first.detector_name}' caught failure: {first.explanation}", reports

        # 1. Compare actual state with expected_final_state
        state_matched, reason = check_subset_match(
            actual_state, data["expected_final_state"]
        )
        if not state_matched:
            return "FAIL", f"Final state mismatch: {reason}", reports

        # 2. Check pending confirmation expectation if specified
        if "expected_pending_confirmation" in data:
            expected_pending = data["expected_pending_confirmation"]
            if expected_pending is None:
                if actual_pending is not None:
                    return (
                        "FAIL",
                        f"Expected no pending confirmation, but got {actual_pending}",
                        reports,
                    )
            else:
                if actual_pending is None:
                    return "FAIL", "Expected pending confirmation, but got None", reports
                matched, reason = check_subset_match(
                    actual_pending, expected_pending, "pending"
                )
                if not matched:
                    return "FAIL", f"Pending message mismatch: {reason}", reports

        # 3. Check expected fault triggered if specified
        if "expected_fault_triggered" in data:
            fault_matched, reason = check_fault_triggered(
                trace, data["expected_fault_triggered"]
            )
            if not fault_matched:
                return "FAIL", reason, reports

        return "PASS", "", []
    except Exception as exc:
        return "FAIL", f"Execution exception: {exc}", []
    finally:
        clear_faults()
        clear_pending_message()
        reset_state()


def main():
    args = sys.argv[1:]
    if args:
        scenario_files = []
        for arg in args:
            p = Path(arg)
            if p.is_dir():
                scenario_files.extend(sorted(p.glob("*.json")))
            elif p.is_file():
                scenario_files.append(p)
            else:
                scenario_files.extend(sorted(Path().glob(arg)))
    else:
        scenarios_dir = Path("scenarios")
        scenario_files = sorted(scenarios_dir.glob("*.json"))

    if not scenario_files:
        print("No scenario files found.")
        sys.exit(1)

    print(f"Running {len(scenario_files)} scenarios...\n")

    passed_count = 0
    failed_count = 0
    detected_count = 0

    for path in scenario_files:
        scenario_id = path.stem
        status, msg, reports = run_scenario(path)

        if status == "PASS":
            print(f"[PASS] {scenario_id}")
            passed_count += 1
        elif status == "DETECTED":
            print(f"[DETECTED FAILURE] {scenario_id}: {msg}")
            for r in reports:
                print(str(r))
            detected_count += 1
        else:
            print(f"[FAIL] {scenario_id}: {msg}")
            for r in reports:
                print(str(r))
            failed_count += 1

    print(
        f"\nSummary: {len(scenario_files)} scenarios run: "
        f"{passed_count} passed, {detected_count} detected failures, {failed_count} failed."
    )

    # Return non-zero if any scenario failed or any failure was detected
    if failed_count > 0 or detected_count > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
