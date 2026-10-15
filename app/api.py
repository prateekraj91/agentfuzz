from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import run_agent
from app.tools import STATE, reset_state

app = FastAPI(title="AgentFuzz")


class AgentRequest(BaseModel):
    message: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/state")
def get_state():
    return STATE


@app.post("/run")
def run_request(request: AgentRequest):
    reset_state()
    return run_agent(request.message)