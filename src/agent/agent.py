# src/agent/orchestrator.py
from anthropic import Anthropic
from src.tools import route, accommodation, weather

class CyclingTripAgent:
    def __init__(self, client: Anthropic):
        self.client = client
        self.tools = {
            "get_route": route.get_route,
            "find_accommodation": accommodation.find_accommodation,
            "get_weather": weather.get_weather,
        }

    async def chat(self, conversation: list[dict], user_message: str) -> dict:
        """
        Runs one turn: send messages to Claude (with tool definitions),
        handle tool calls, and return updated conversation + agent reply.
        """
        ...
