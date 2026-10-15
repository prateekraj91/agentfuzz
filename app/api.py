
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import run_agent
from app.tools import STATE, reset_state, send_message
from app.trace import log_event
from app.pending import get_pending_message, clear_pending_message

app = FastAPI(title="AgentFuzz")

STATIC_DIR = Path(__file__).parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


class AgentRequest(BaseModel):
    message: str

class ConfirmRequest(BaseModel):
    confirmed: bool

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/state")
def get_state():
    return STATE


@app.post("/run")
def run_request(request: AgentRequest):
    return run_agent(request.message)


@app.post("/reset")
def reset_demo():
    reset_state()
    clear_pending_message()
    return {
        "status": "ok",
        "message": "Demo state reset successfully",
        "state": STATE,
    }

@app.get("/pending")
def get_pending():
    pending = get_pending_message()
    return {"pending": pending}


@app.post("/confirm")
def confirm_message(request: ConfirmRequest):
    pending = get_pending_message()

    if pending is None:
        return {
            "status": "error",
            "message": "No message is awaiting confirmation.",
        }

    if not request.confirmed:
        clear_pending_message()
        return {
            "status": "cancelled",
            "message": "Message cancelled. Nothing was sent.",
        }

    before_state = {"messages": list(STATE["messages"])}

    result = send_message(
        recipient=pending["recipient"],
        message=pending["message"],
    )

    clear_pending_message()

    log_event(
        "confirmation_result",
        {
            "confirmed": True,
            "result": result,
            "state_before": before_state,
            "state_after": {"messages": list(STATE["messages"])},
        },
    )

    return {
        "status": "sent" if result["success"] else "error",
        "result": result,
        "state": STATE,
    }