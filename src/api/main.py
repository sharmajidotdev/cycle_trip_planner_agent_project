# src/api/main.py
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field
from anthropic import Anthropic

from agent.agent import CyclingTripAgent
from models.schemas import TripPlan

load_dotenv()


app = FastAPI()

api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = Anthropic(api_key=api_key) if api_key else None
agent = CyclingTripAgent(client=anthropic_client)


class ChatRequest(BaseModel):
    conversation_id: str = Field(..., description="Client-provided conversation/session identifier")
    message: str = Field(..., min_length=1, description="User prompt for the cycling planner")


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    triplan: TripPlan | None = None
    questions: list[str] | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = await agent.chat(
        conversation_id=req.conversation_id,
        user_message=req.message,
    )
    return ChatResponse(**result)
