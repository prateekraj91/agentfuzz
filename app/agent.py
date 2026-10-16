
import json
import ollama

from app.tools import (
    STATE,
    move_meeting,
    create_reminder,
    send_message,
    set_device_state,
    add_shopping_item,
    get_shopping_list,
)
from copy import deepcopy
from app.trace import log_event
from app.pending import set_pending_message, get_pending_message
from app.faults import apply_fault

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
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "Prepare a message for a recipient. "
                "Do not send until the user confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Message recipient",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message content",
                    },
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_device_state",
            "description": (
                "Turn a smart-home device (such as a light) on or off."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "Device identifier or name, e.g. 'living_room_light'",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Target status ('on' or 'off')",
                    },
                },
                "required": ["device", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_shopping_item",
            "description": "Add an item to the shopping list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "Name of the item to add to the shopping list",
                    },
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shopping_list",
            "description": "View all items currently on the shopping list.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "move_meeting": move_meeting,
    "create_reminder": create_reminder,
    "send_message": send_message,
    "set_device_state": set_device_state,
    "add_shopping_item": add_shopping_item,
    "get_shopping_list": get_shopping_list,
}


def run_agent(user_request: str, options: dict | None = None) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a home assistant. "
                "The current simulated date is 2026-10-15. "
                "The calendar contains meeting_1, Project Meeting, "
                "at 17:00. You manage calendar, reminders, messages, "
                "smart-home devices (e.g. living_room_light, kitchen_light), "
                "and the shopping list. Use tools to perform requested actions. "
                "Only claim actions succeeded when tool results confirm them. "
                "For this prototype, interpret relative times using the "
                "simulated meeting time. Call tools as needed."
            ),
        },
        {"role": "user", "content": user_request},
    ]

    trace = []
    call_step = 0

    for step in range(6):
        chat_kwargs = {
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
        }
        if options is not None:
            chat_kwargs["options"] = options

        response = ollama.chat(**chat_kwargs)

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
            call_step += 1

            fault = apply_fault(name, args)

            if fault is None and name == "send_message":
                if get_pending_message() is not None:
                    return {
                        "reply": (
                            "A message is already awaiting confirmation. "
                            "Please confirm or cancel it before sending "
                            "another."
                        ),
                        "trace": trace,
                        "state": STATE,
                    }

                set_pending_message(
                    recipient=args.get("recipient", ""),
                    message=args.get("message", ""),
                )
                pending_result = {
                    "success": False,
                    "pending_confirmation": True,
                    "message": "Waiting for user confirmation.",
                }
                trace.append({
                    "step": call_step,
                    "turn": step + 1,
                    "tool": name,
                    "arguments": args,
                    "result": pending_result,
                    "state_before": deepcopy(STATE),
                    "state_after": deepcopy(STATE),
                })
                return {
                    "reply": (
                        f"Please confirm sending this message to "
                        f"{args.get('recipient', '')}: "
                        f"{args.get('message', '')}"
                    ),
                    "pending_confirmation": {
                        "recipient": args.get("recipient", ""),
                        "message": args.get("message", ""),
                    },
                    "trace": trace,
                    "state": STATE,
                }

            before_state = deepcopy(STATE)
            log_event("tool_call", {
                "step": call_step,
                "turn": step + 1,
                "tool": name,
                "arguments": args,
            })

            if fault is not None:
                result = fault
            elif name not in TOOL_FUNCTIONS:
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
                "step": call_step,
                "turn": step + 1,
                "tool": name,
                "result": result,
                "state_before": before_state,
                "state_after": deepcopy(STATE),
            })

            trace.append({
                "step": call_step,
                "turn": step + 1,
                "tool": name,
                "arguments": args,
                "result": result,
                "state_before": before_state,
                "state_after": deepcopy(STATE),
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

