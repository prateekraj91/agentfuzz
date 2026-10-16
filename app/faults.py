"""Deterministic fault injection for AgentFuzz."""

from copy import deepcopy

SUPPORTED_FAULTS = {"timeout", "conflict", "missing_data"}

_active_faults: list[dict] = []
_triggered: set[int] = set()


def set_faults(faults: list[dict] | None) -> None:
    """Configure faults for a scenario and reset trigger tracking."""
    global _active_faults, _triggered
    _active_faults = deepcopy(faults or [])
    _triggered = set()


def clear_faults() -> None:
    """Disable fault injection."""
    set_faults([])


def apply_fault(tool_name: str, arguments: dict | None = None) -> dict | None:
    """Return a simulated error for the first matching, not-yet-triggered fault;

    return None if no configured fault matches.
    """
    args = arguments if isinstance(arguments, dict) else {}

    for index, fault in enumerate(_active_faults):
        if index in _triggered or fault.get("tool") != tool_name:
            continue

        fault_type = fault.get("type")
        seed = fault.get("seed")

        if fault_type not in SUPPORTED_FAULTS:
            _triggered.add(index)
            return {
                "success": False,
                "error": f"Unsupported fault type: {fault_type}",
            }

        if not isinstance(seed, int) or isinstance(seed, bool):
            _triggered.add(index)
            return {
                "success": False,
                "error": "Fault seed must be an integer",
            }

        if fault_type == "conflict" and tool_name != "move_meeting":
            _triggered.add(index)
            return {
                "success": False,
                "error": "Conflict fault requires move_meeting",
            }

        _triggered.add(index)
        metadata = {"type": fault_type, "seed": seed}

        if fault_type == "timeout":
            error = "Simulated timeout"
        elif fault_type == "conflict":
            error = "Calendar conflict: another event occupies that time"
        elif tool_name == "send_message":
            error = f"Contact not found: {args.get('recipient', '')}"
        elif tool_name == "set_device_state":
            error = f"Device data is missing: {args.get('device', '')}"
        else:
            error = "Required data is missing"

        return {
            "success": False,
            "error": error,
            "fault": metadata,
        }

    return None
