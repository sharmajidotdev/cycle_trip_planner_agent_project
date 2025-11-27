import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from agent.prompts import SYSTEM_PROMPT
from models.schemas import (
    AccommodationRequest,
    AccommodationResponse,
    RouteRequest,
    RouteResponse,
    WeatherRequest,
    WeatherResponse,
)
from tools import accomodation, route, weather


class CyclingTripAgent:
    """
    Minimal tool-aware agent configured for Anthropic tool use, currently
    returning mocked tool outputs for a deterministic response.
    """

    def __init__(self, client: Optional[Anthropic] = None):
        self.client = client
        self.tools: Dict[str, Callable[..., Any]] = {
            "get_route": route.get_route,
            "find_accommodation": accomodation.find_accommodation,
            "get_weather": weather.get_weather,
        }
        self.tool_input_models: Dict[str, Any] = {
            "get_route": RouteRequest,
            "find_accommodation": AccommodationRequest,
            "get_weather": WeatherRequest,
        }
        self.tool_specs = self._build_tool_specs()

    def _schema(self, model_cls: Any) -> Dict[str, Any]:
        """
        Support both Pydantic v1 and v2 style schema generation.
        """
        if hasattr(model_cls, "model_json_schema"):
            return model_cls.model_json_schema()
        return model_cls.schema()

    def _block_attr(self, block: Any, attr: str) -> Any:
        if isinstance(block, dict):
            return block.get(attr)
        return getattr(block, attr, None)

    def _block_type(self, block: Any) -> Optional[str]:
        return self._block_attr(block, "type")

    def _build_tool_specs(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_route",
                "description": "Plan a multi-day cycling route between start and end points.",
                "input_schema": self._schema(RouteRequest),
            },
            {
                "name": "find_accommodation",
                "description": "Find places to stay near a segment end point.",
                "input_schema": self._schema(AccommodationRequest),
            },
            {
                "name": "get_weather",
                "description": "Get the weather outlook for a location on a given day.",
                "input_schema": self._schema(WeatherRequest),
            },
        ]

    async def _call_llm(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> Any:
        if not self.client:
            raise RuntimeError("Anthropic client not configured")
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        return await asyncio.to_thread(
            self.client.messages.create,
            model=model,
            max_tokens=512,
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"},
            system=system,
        )

    async def _execute_tool(self, call: Dict[str, Any]) -> Dict[str, Any]:
        name = call.get("name")
        input_payload = call.get("input", {})
        tool_fn = self.tools.get(name)
        input_model = self.tool_input_models.get(name)
        if not tool_fn or not input_model:
            raise ValueError(f"Unknown tool requested: {name}")
        typed_input = input_model(**input_payload)
        result = await tool_fn(typed_input)
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return result.dict()

    async def chat(self, conversation_id: str, user_message: str) -> dict:
        """
        Runs a full tool-enabled exchange with Anthropic: send the user
        message, execute any requested tools, and return the assistant reply
        plus the tool outputs used to form the plan.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": [{"type": "text", "text": user_message}]}
        ]

        first_response = await self._call_llm(
            messages=messages, tools=self.tool_specs, system=SYSTEM_PROMPT
        )

        tool_calls = [
            item for item in first_response.content if self._block_type(item) == "tool_use"
        ]

        tool_results_payload: List[Dict[str, Any]] = []
        plan: Dict[str, Any] = {}

        for call in tool_calls:
            call_name = self._block_attr(call, "name")
            call_id = self._block_attr(call, "id")
            call_input = self._block_attr(call, "input") or {}
            if not call_name:
                continue
            output = await self._execute_tool({"name": call_name, "input": call_input})
            plan[call_name] = output
            tool_results_payload.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": [{"type": "text", "text": json.dumps(output)}],
                }
            )

        # If tools were called, send results back for a final answer.
        if tool_results_payload:
            messages.append({"role": "assistant", "content": first_response.content})
            messages.append({"role": "user", "content": tool_results_payload})
            final_response = await self._call_llm(
                messages=messages, tools=self.tool_specs, system=SYSTEM_PROMPT
            )
            content_blocks = [
                self._block_attr(block, "text") or ""
                for block in final_response.content
                if self._block_type(block) == "text"
            ]
            reply_text = "".join(content_blocks).strip()
        else:
            # No tools requested; use the first response text directly.
            content_blocks = [
                self._block_attr(block, "text") or ""
                for block in first_response.content
                if self._block_type(block) == "text"
            ]
            reply_text = "".join(content_blocks).strip()

        return {
            "conversation_id": conversation_id,
            "reply": reply_text,
            "plan": plan or None,
        }
