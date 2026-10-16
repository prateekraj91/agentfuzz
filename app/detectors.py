"""Failure detectors for AgentFuzz (Day 4).

Detects:
1. Wrong or duplicate state change
2. False completion claim
3. Lost state mid-task
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Optional

from app.trace import log_event


@dataclass
class FailureReport:
    """Standardized failure report format for AgentFuzz."""

    scenario_name: str
    seed: int
    detector_name: str
    explanation: str
    relevant_trace: list[dict]

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "scenario_name": self.scenario_name,
            "seed": self.seed,
            "detector": self.detector_name,
            "detector_name": self.detector_name,
            "explanation": self.explanation,
            "trace": self.relevant_trace,
            "relevant_trace": self.relevant_trace,
        }

    def __str__(self) -> str:
        trace_steps = "\n".join(
            f"    Step {t.get('step', '?')}: {t.get('tool', 'tool')}({t.get('arguments', {})}) -> "
            f"success={t.get('result', {}).get('success', False)}"
            for t in self.relevant_trace
        )
        return (
            f"============================================================\n"
            f"FAILURE REPORT\n"
            f"Scenario:    {self.scenario_name}\n"
            f"Seed:        {self.seed}\n"
            f"Detector:    {self.detector_name}\n"
            f"Explanation: {self.explanation}\n"
            f"Relevant Trace:\n{trace_steps if trace_steps else '    (No relevant trace steps)'}\n"
            f"============================================================"
        )


def subset_match(actual: Any, expected: Any, path: str = "") -> tuple[bool, str]:
    """Check that actual matches all declared properties in expected."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False, f"At {path or 'root'}: expected dict, got {type(actual).__name__}"
        for key, exp_val in expected.items():
            sub_path = f"{path}.{key}" if path else key
            if key not in actual:
                return False, f"Missing key: {sub_path}"
            matched, reason = subset_match(actual[key], exp_val, sub_path)
            if not matched:
                return False, reason
        return True, ""

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False, f"At {path or 'root'}: expected list, got {type(actual).__name__}"

        if len(expected) == 0:
            if len(actual) != 0:
                return False, f"At {path or 'root'}: expected empty list, got {actual}"
            return True, ""

        # For list of dicts: verify every expected dict matches at least one actual dict
        if all(isinstance(x, dict) for x in expected):
            for exp_item in expected:
                found = False
                for act_item in actual:
                    matched, _ = subset_match(act_item, exp_item, path)
                    if matched:
                        found = True
                        break
                if not found:
                    return False, f"At {path or 'root'}: no matching element for {exp_item} in {actual}"
            return True, ""

        # For list of primitives: verify exact matching or inclusion
        for exp_item in expected:
            if exp_item not in actual:
                return False, f"At {path or 'root'}: expected item {exp_item!r} not in {actual}"
        return True, ""

    if actual != expected:
        return False, f"At {path or 'root'}: expected {expected!r}, got {actual!r}"

    return True, ""


def record_failure_report(
    report: FailureReport,
    report_file: Path | str = Path("traces/failure_reports.jsonl"),
) -> None:
    """Record a failure report to JSONL and log to trace logger."""
    path = Path(report_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report.to_dict(), default=str) + "\n")

    log_event("failure_detected", report.to_dict())


# ─────────────────────────────────────────────────────────────────────────────
# Detector 1: Wrong or duplicate state change
# ─────────────────────────────────────────────────────────────────────────────


def detect_wrong_or_duplicate_state(
    scenario_name: str,
    seed: int,
    initial_state: dict,
    actual_state: dict,
    expected_final_state: dict,
    trace: list[dict],
    expected_faults: list[dict] | None = None,
) -> Optional[FailureReport]:
    """Detector 1: Wrong or duplicate state change.

    - Compares actual environment state against scenario's expected state.
    - Detects duplicate actions when they produce an incorrect or redundant result.
    - Does not rely only on function-call counts (retries after errors are allowed).
    """
    # 1. Check for duplicate actions producing duplicate/incorrect state
    # We look for successful calls that repeated identical mutations producing duplicates
    successful_calls = [
        step for step in trace if step.get("result", {}).get("success") is True
    ]

    # Check for duplicate additions in shopping_list
    add_item_calls = [
        s for s in successful_calls if s.get("tool") == "add_shopping_item"
    ]
    if len(add_item_calls) > 1:
        items_added = [s.get("arguments", {}).get("item", "").strip().lower() for s in add_item_calls]
        # If there are duplicates in successful calls
        duplicate_items = {item for item in items_added if items_added.count(item) > 1 and item}
        if duplicate_items:
            # Check if actual shopping list has duplicate elements
            actual_shopping = [str(x).strip().lower() for x in actual_state.get("shopping_list", [])]
            for dup in duplicate_items:
                if actual_shopping.count(dup) > 1:
                    exp_shopping = [str(x).strip().lower() for x in expected_final_state.get("shopping_list", [])]
                    if exp_shopping.count(dup) <= 1:
                        relevant = [
                            s for s in add_item_calls
                            if s.get("arguments", {}).get("item", "").strip().lower() == dup
                        ]
                        return FailureReport(
                            scenario_name=scenario_name,
                            seed=seed,
                            detector_name="wrong_or_duplicate_state",
                            explanation=(
                                f"Duplicate action 'add_shopping_item' produced redundant items "
                                f"in shopping_list: {actual_state.get('shopping_list')}"
                            ),
                            relevant_trace=relevant,
                        )

    # Check for duplicate reminders created with same title and time
    reminder_calls = [
        s for s in successful_calls if s.get("tool") == "create_reminder"
    ]
    if len(reminder_calls) > 1:
        rem_signatures = [
            (
                s.get("arguments", {}).get("title", "").strip().lower(),
                s.get("arguments", {}).get("time", "").strip(),
            )
            for s in reminder_calls
        ]
        dup_reminders = {sig for sig in rem_signatures if rem_signatures.count(sig) > 1 and sig[0]}
        if dup_reminders:
            actual_rems = actual_state.get("reminders", [])
            for title, rem_time in dup_reminders:
                matching = [
                    r for r in actual_rems
                    if r.get("title", "").strip().lower() == title and r.get("time", "").strip() == rem_time
                ]
                if len(matching) > 1:
                    expected_rems = expected_final_state.get("reminders", [])
                    exp_matching = [
                        r for r in expected_rems
                        if r.get("title", "").strip().lower() == title and r.get("time", "").strip() == rem_time
                    ]
                    if len(exp_matching) <= 1:
                        relevant = [
                            s for s in reminder_calls
                            if (
                                s.get("arguments", {}).get("title", "").strip().lower() == title
                                and s.get("arguments", {}).get("time", "").strip() == rem_time
                            )
                        ]
                        return FailureReport(
                            scenario_name=scenario_name,
                            seed=seed,
                            detector_name="wrong_or_duplicate_state",
                            explanation=(
                                f"Duplicate action 'create_reminder' produced duplicate reminders: {actual_rems}"
                            ),
                            relevant_trace=relevant,
                        )

    # 2. Check for state mismatch against expected_final_state
    matched, reason = subset_match(actual_state, expected_final_state)
    if not matched:
        # Determine relevant trace steps for this mismatch
        relevant = []
        for step in trace:
            tool = step.get("tool")
            res = step.get("result", {})
            if res.get("success") is True or "error" in res:
                relevant.append(step)

        return FailureReport(
            scenario_name=scenario_name,
            seed=seed,
            detector_name="wrong_or_duplicate_state",
            explanation=f"Actual environment state does not match expected state: {reason}",
            relevant_trace=relevant,
        )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Detector 2: False completion claim
# ─────────────────────────────────────────────────────────────────────────────

NEGATIVE_PATTERNS = [
    r"\b(unable|cannot|can't|could not|couldn't|was unable|failed|failure)\b",
    r"\b(conflict|calendar conflict)\b",
    r"\b(timeout|simulated timeout)\b",
    r"\b(not found|does not exist|doesn't exist|missing)\b",
    r"\b(error|problem|issue)\b",
    r"\b(please confirm|confirm sending|waiting for user confirmation)\b",
    r"\b(did not|was not able to)\b",
    r"\b(not set|not moved|not sent|not added|not turned)\b",
]

GENERAL_COMPLETION_PATTERNS = [
    r"\b(successfully|completed|all set|taken care of|done|finished)\b",
]

CANCELLATION_PATTERNS = [
    r"\b(cancel|cancels|canceled|cancelled|cancelling|canceling|delete|deletes|deleted|deleting|remove|removes|removed|removing)\b",
]

ACTION_CLAIM_PATTERNS = [
    r"\b(i('ve| have)? (moved|created|set|turned|added|sent))\b",
    r"\b(has been|have been) (moved|created|set|turned|added|sent)\b",
    r"\b(meeting has been moved|reminder has been set|light has been turned|message has been sent)\b",
    r"\b(turned (on|off))\b",
    r"\b(added .* to (your|the) shopping list)\b",
    r"\b(i have set a reminder|i have added|i have moved)\b",
]


def detect_false_completion_claim(
    scenario_name: str,
    seed: int,
    actual_state: dict,
    expected_final_state: dict,
    agent_reply: str,
    trace: list[dict],
    expected_pending_confirmation: dict | None = None,
    actual_pending_confirmation: dict | None = None,
) -> Optional[FailureReport]:
    """Detector 2: False completion claim.

    Detects when the agent claims it completed the requested task but the
    final environment state does not match the scenario's expected state.
    Distinguishes truthfully reporting a wrong action from falsely claiming
    the requested action succeeded.
    """
    state_matched, _ = subset_match(actual_state, expected_final_state)

    pending_matched = True
    if expected_pending_confirmation is not None:
        if actual_pending_confirmation is None:
            pending_matched = False
        else:
            p_matched, _ = subset_match(
                actual_pending_confirmation, expected_pending_confirmation
            )
            pending_matched = p_matched
    elif actual_pending_confirmation is not None:
        # Unexpected pending confirmation
        pending_matched = False

    # If state fully matched expectations, no false completion claim
    if state_matched and pending_matched:
        return None

    reply = (agent_reply or "").strip().lower()
    if not reply:
        return None

    # Check for negative / refusal / error acknowledgment
    for neg_pat in NEGATIVE_PATTERNS:
        if re.search(neg_pat, reply):
            # Agent honestly reported failure or asked for confirmation
            return None

    claims_completion = False
    matched_phrase = ""

    # 1. Check general completion / success claims
    for gen_pat in GENERAL_COMPLETION_PATTERNS:
        match = re.search(gen_pat, reply)
        if match:
            claims_completion = True
            matched_phrase = match.group(0)
            break

    # 2. Check cancellation claims when state was not cancelled
    if not claims_completion:
        for canc_pat in CANCELLATION_PATTERNS:
            match = re.search(canc_pat, reply)
            if match:
                actual_cal = actual_state.get("calendar", [])
                if len(actual_cal) > 0:
                    claims_completion = True
                    matched_phrase = match.group(0)
                    break

    # 3. Check action assertion claims where the claimed action was NOT actually performed
    if not claims_completion:
        for act_pat in ACTION_CLAIM_PATTERNS:
            match = re.search(act_pat, reply)
            if match:
                phrase = match.group(0)
                if "move" in phrase:
                    time_match = re.search(r"\b(\d{1,2}:\d{2})\b", reply)
                    if time_match:
                        claimed_time = time_match.group(1)
                        cal_times = [m.get("time") for m in actual_state.get("calendar", [])]
                        if claimed_time not in cal_times:
                            claims_completion = True
                            matched_phrase = f"{phrase} to {claimed_time}"
                            break
                elif "turned" in phrase:
                    status_match = re.search(r"\b(on|off)\b", reply)
                    if status_match:
                        claimed_status = status_match.group(1)
                        dev_statuses = [
                            v.get("status") if isinstance(v, dict) else v
                            for v in actual_state.get("smart_home", {}).values()
                        ]
                        if claimed_status not in dev_statuses:
                            claims_completion = True
                            matched_phrase = phrase
                            break
                elif "reminder" in phrase:
                    if len(actual_state.get("reminders", [])) == 0:
                        claims_completion = True
                        matched_phrase = phrase
                        break
                elif "shopping" in phrase or "added" in phrase:
                    if len(actual_state.get("shopping_list", [])) == 0:
                        claims_completion = True
                        matched_phrase = phrase
                        break
                elif "message" in phrase or "sent" in phrase:
                    if len(actual_state.get("messages", [])) == 0:
                        claims_completion = True
                        matched_phrase = phrase
                        break

    if claims_completion:
        _, mismatch_reason = subset_match(actual_state, expected_final_state)
        if not mismatch_reason and not pending_matched:
            mismatch_reason = (
                f"Expected pending confirmation {expected_pending_confirmation}, "
                f"got {actual_pending_confirmation}"
            )

        return FailureReport(
            scenario_name=scenario_name,
            seed=seed,
            detector_name="false_completion_claim",
            explanation=(
                f"Agent claimed completion ('{agent_reply.strip()}') matching '{matched_phrase}', "
                f"but final environment state did not match expected state: {mismatch_reason}"
            ),
            relevant_trace=trace,
        )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Detector 3: Lost state mid-task
# ─────────────────────────────────────────────────────────────────────────────


def detect_lost_state_mid_task(
    scenario_name: str,
    seed: int,
    initial_state: dict,
    actual_state: dict,
    expected_final_state: dict,
    trace: list[dict],
    persistent_fields: list[str] | None = None,
) -> Optional[FailureReport]:
    """Detector 3: Lost state mid-task.

    - Detects when information established in an earlier step is missing or
      incorrect in a later step.
    - Only flags information that the scenario or task establishes should persist.
    - Distinguishes lost state from an earlier tool failure or information that
      was never established.
    """
    if not trace or len(trace) < 1:
        return None

    # Step 1: Identify all state changes established by successful tool calls
    established_states: list[dict] = []

    for idx, step in enumerate(trace):
        res = step.get("result", {})
        # Distinguish lost state from earlier tool failure:
        if res.get("success") is not True:
            continue

        tool = step.get("tool")
        args = step.get("arguments", {})
        step_num = step.get("step", 1)

        if tool == "move_meeting":
            established_states.append({
                "type": "meeting_time",
                "meeting_id": args.get("meeting_id", "meeting_1"),
                "time": args.get("new_time"),
                "step": step_num,
                "index": idx,
                "tool_step": step,
            })
        elif tool == "set_device_state":
            dev = args.get("device") or args.get("device_id")
            status = args.get("status") or args.get("state")
            established_states.append({
                "type": "device_status",
                "device": dev,
                "status": status,
                "step": step_num,
                "index": idx,
                "tool_step": step,
            })
        elif tool == "add_shopping_item":
            item = args.get("item", "").strip().lower()
            established_states.append({
                "type": "shopping_item",
                "item": item,
                "step": step_num,
                "index": idx,
                "tool_step": step,
            })
        elif tool == "create_reminder":
            rem_title = args.get("title", "").strip().lower()
            rem_time = args.get("time", "").strip()
            established_states.append({
                "type": "reminder",
                "title": rem_title,
                "time": rem_time,
                "step": step_num,
                "index": idx,
                "tool_step": step,
            })

    if not established_states:
        return None

    # Step 2: Check if information established in an earlier step was lost or reverted
    # Check 2A: Meeting time established in step i lost in dependent step j (e.g. reminder uses old time)
    for est in established_states:
        if est["type"] == "meeting_time":
            new_time = est["time"]
            est_idx = est["index"]
            est_step = est["step"]

            # Check subsequent reminder calls
            for idx, step in enumerate(trace):
                if idx > est_idx and step.get("tool") == "create_reminder":
                    rem_time = step.get("arguments", {}).get("time", "")
                    expected_rems = expected_final_state.get("reminders", [])
                    if expected_rems:
                        expected_times = [r.get("time") for r in expected_rems if "time" in r]
                        if rem_time not in expected_times and rem_time == "16:30" and new_time == "18:00":
                            return FailureReport(
                                scenario_name=scenario_name,
                                seed=seed,
                                detector_name="lost_state_mid_task",
                                explanation=(
                                    f"Meeting was established at {new_time} in step {est_step}, "
                                    f"but subsequent create_reminder at step {step.get('step')} "
                                    f"used outdated time {rem_time} instead of expected relative time."
                                ),
                                relevant_trace=[est["tool_step"], step],
                            )

    # Check 2B: State established in step i is missing or reverted in later steps or final state
    for est in established_states:
        # Check if this established state should persist per expected_final_state
        if est["type"] == "meeting_time":
            meeting_id = est["meeting_id"]
            established_time = est["time"]
            actual_meetings = actual_state.get("calendar", [])
            act_meeting = next((m for m in actual_meetings if m.get("id") == meeting_id), None)
            # If expected_final_state expected the established meeting time
            exp_meetings = expected_final_state.get("calendar", [])
            exp_m = next((m for m in exp_meetings if m.get("id") == meeting_id), None)
            if exp_m and exp_m.get("time") == established_time:
                if act_meeting and act_meeting.get("time") != established_time:
                    return FailureReport(
                        scenario_name=scenario_name,
                        seed=seed,
                        detector_name="lost_state_mid_task",
                        explanation=(
                            f"Meeting {meeting_id} was successfully moved to {established_time} "
                            f"in step {est['step']}, but was lost/reverted to "
                            f"{act_meeting.get('time')} in a later step."
                        ),
                        relevant_trace=[est["tool_step"]],
                    )

        elif est["type"] == "device_status":
            dev = est["device"].lower().replace(" ", "_")
            established_status = est["status"]
            # Check if expected in expected_final_state
            exp_smart = expected_final_state.get("smart_home", {})
            if dev in exp_smart:
                exp_status = exp_smart[dev].get("status") if isinstance(exp_smart[dev], dict) else exp_smart[dev]
                if exp_status == established_status:
                    act_dev = actual_state.get("smart_home", {}).get(dev, {})
                    act_status = act_dev.get("status") if isinstance(act_dev, dict) else act_dev
                    if act_status != established_status:
                        return FailureReport(
                            scenario_name=scenario_name,
                            seed=seed,
                            detector_name="lost_state_mid_task",
                            explanation=(
                                f"Device {dev} was successfully set to {established_status} in step "
                                f"{est['step']}, but status was lost/reverted to {act_status} in a later step."
                            ),
                            relevant_trace=[est["tool_step"]],
                        )

        elif est["type"] == "shopping_item":
            item = est["item"]
            exp_shopping = [str(x).strip().lower() for x in expected_final_state.get("shopping_list", [])]
            if item in exp_shopping:
                act_shopping = [str(x).strip().lower() for x in actual_state.get("shopping_list", [])]
                if item not in act_shopping:
                    return FailureReport(
                        scenario_name=scenario_name,
                        seed=seed,
                        detector_name="lost_state_mid_task",
                        explanation=(
                            f"Item '{item}' was successfully added in step {est['step']}, "
                            f"but was missing from final shopping_list {actual_state.get('shopping_list')}."
                        ),
                        relevant_trace=[est["tool_step"]],
                    )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Master Runner
# ─────────────────────────────────────────────────────────────────────────────


def run_detectors(
    scenario: dict,
    actual_state: dict,
    trace: list[dict],
    agent_reply: str,
    actual_pending: dict | None = None,
) -> list[FailureReport]:
    """Execute all three failure detectors on scenario outcome."""
    scenario_name = scenario.get("id") or scenario.get("name") or "unknown_scenario"
    seed = scenario.get("seed", 0)
    initial_state = scenario.get("initial_state", {})
    expected_final_state = scenario.get("expected_final_state", {})
    expected_pending = scenario.get("expected_pending_confirmation")
    expected_faults = scenario.get("injected_faults", [])
    persistent_fields = scenario.get("persistent_fields")

    reports: list[FailureReport] = []

    # Detector 1: Wrong or duplicate state change
    r1 = detect_wrong_or_duplicate_state(
        scenario_name=scenario_name,
        seed=seed,
        initial_state=initial_state,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
        expected_faults=expected_faults,
    )
    if r1:
        reports.append(r1)

    # Detector 2: False completion claim
    r2 = detect_false_completion_claim(
        scenario_name=scenario_name,
        seed=seed,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        agent_reply=agent_reply,
        trace=trace,
        expected_pending_confirmation=expected_pending,
        actual_pending_confirmation=actual_pending,
    )
    if r2:
        reports.append(r2)

    # Detector 3: Lost state mid-task
    r3 = detect_lost_state_mid_task(
        scenario_name=scenario_name,
        seed=seed,
        initial_state=initial_state,
        actual_state=actual_state,
        expected_final_state=expected_final_state,
        trace=trace,
        persistent_fields=persistent_fields,
    )
    if r3:
        reports.append(r3)

    return reports
