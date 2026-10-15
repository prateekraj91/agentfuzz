
import json
import ollama

from app.tools import STATE, move_meeting, create_reminder
from copy import deepcopy
from app.trace import log_event

MODEL = "qwen2.5:7b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_meeting",
            "description": (
                "Move the existing Project Meeting. "
                "Its exact meeting_id is 'meeting_1'. "
                "Always use meeting_id='meeting_1' for this meeting."

            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_id": {
                        "type": "string",
                        "description": "ID of the meeting to move",
                    },
                    "new_time": {
                        "type": "string",
                        "description": "Time in 24-hour HH:MM format, e.g. 18:00",
                    },
                },
                "required": ["meeting_id", "new_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a reminder at a specified time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "time": {
                        "type": "string",
                        "description": "Time in 24-hour HH:MM format, e.g. 18:00",
                    },
                },
                "required": ["title", "time"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "move_meeting": move_meeting,
    "create_reminder": create_reminder,
}


def run_agent(user_request: str) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a home assistant. "
                "The current simulated date is 2026-10-15. "
                "The calendar contains meeting_1, Project Meeting, "
                "at 17:00. Use tools to perform requested actions. "
                "Only claim actions succeeded when tool results confirm them. "
                "For this prototype, interpret relative times using the "
                "simulated meeting time. Call tools as needed."
            ),
        },
        {"role": "user", "content": user_request},
    ]

    trace = []

    for step in range(6):
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )

        message = response.message
        log_event("model_message", {
            "step": step + 1,
            "content": message.content,
            "tool_calls": [
                {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
                for call in (message.tool_calls or [])
            ],
        })
        messages.append(message)

        if not message.tool_calls:
            return {
                "reply": message.content,
                "trace": trace,
                "state": STATE,
            }

        for call in message.tool_calls:
            name = call.function.name
            args = call.function.arguments
            before_state = deepcopy(STATE)
            log_event("tool_call", {
                "step": step + 1,
                "tool": name,
                "arguments": args,
            })

            if name not in TOOL_FUNCTIONS:
                result = {"success": False, "error": "Unknown tool"}
            else:
                try:
                    result = TOOL_FUNCTIONS[name](**args)
                except (TypeError, ValueError) as exc:
                    result = {
                        "success": False,
                        "error": f"Invalid arguments: {exc}",
                    }

            log_event("tool_result", {
                "step": step + 1,
                "tool": name,
                "result": result,
                "state_before": before_state,
                "state_after": deepcopy(STATE),
            })

            trace.append({
                "step": step + 1,
                "tool": name,
                "arguments": args,
                "result": result,
            })

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result),
            })

    return {
        "reply": "Stopped: maximum tool-call steps reached.",
        "trace": trace,
        "state": STATE,
    }

