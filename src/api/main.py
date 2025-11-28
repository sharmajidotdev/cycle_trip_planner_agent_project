# src/api/main.py
import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from anthropic import Anthropic
from fastapi.middleware.cors import CORSMiddleware

from agent.agent import CyclingTripAgent
from models.schemas import TripPlan

load_dotenv()


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/chat/stream")
async def chat_stream(conversation_id: str, message: str):
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def progress(evt: dict) -> None:
            await queue.put(evt)

        async def run_agent() -> None:
            try:
                result = await agent.chat(
                    conversation_id=conversation_id,
                    user_message=message,
                    progress_cb=progress,
                )
                final_payload = {
                    "stage": "done",
                    "reply": result.get("reply"),
                    "questions": result.get("questions"),
                    "tool_calls": result.get("tool_calls"),
                }
                triplan = result.get("triplan")
                if triplan:
                    final_payload["triplan"] = triplan.model_dump() if hasattr(triplan, "model_dump") else triplan
                await queue.put(final_payload)
            except Exception as exc:
                await queue.put({"stage": "error", "message": str(exc)})
            finally:
                await queue.put(None)

        runner = asyncio.create_task(run_agent())
        try:
            while True:
                evt = await queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt)}\n\n"
        finally:
            runner.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
