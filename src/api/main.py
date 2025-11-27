# src/api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent.agent import CyclingTripAgent

app = FastAPI()
agent = CyclingTripAgent(...)

class ChatRequest(BaseModel):
    conversation_id: str
    message: str

class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    plan: dict | None = None 

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    result = await agent.chat(
        conversation_id=req.conversation_id,
        user_message=req.message,
    )
    return result
