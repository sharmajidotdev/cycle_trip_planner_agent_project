import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from agent.logger import log_event
from agent.memory import InMemoryConversationMemory, MemoryMessage, to_claude_messages
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
        self.memory = InMemoryConversationMemory(max_messages=50)

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
        prior = self.memory.get_history(conversation_id)
        prior_state = self.memory.get_state(conversation_id)
        last_plan_summary = prior_state.get("last_plan_summary")
        user_msg = MemoryMessage(
            role="user", content=[{"type": "text", "text": user_message}]
        )
        messages: List[Dict[str, Any]] = to_claude_messages(prior)
        if last_plan_summary:
            messages.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"Previous plan summary:\n{last_plan_summary}"}],
                }
            )
        messages.append(
            {"role": user_msg.role, "content": user_msg.content}
        )
        log_event(
            conversation_id,
            "user_message",
            {
                "message": user_message,
                "history_count": len(prior),
                "has_last_plan_summary": bool(last_plan_summary),
            },
        )

        first_response = await self._call_llm(
            messages=messages, tools=self.tool_specs, system=SYSTEM_PROMPT
        )

        tool_calls = [
            item for item in first_response.content if self._block_type(item) == "tool_use"
        ]
        log_event(
            conversation_id,
            "tool_calls",
            {
                "requested": [
                    {
                        "id": self._block_attr(call, "id"),
                        "name": self._block_attr(call, "name"),
                        "input": self._block_attr(call, "input"),
                    }
                    for call in tool_calls
                ]
            },
        )

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
            log_event(
                conversation_id,
                "tool_result",
                {"name": call_name, "id": call_id, "output": output},
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

        if not reply_text:
            if plan:
                reply_text = "Here are the tool results:\n" + json.dumps(plan, indent=2)
            else:
                reply_text = "I wasn't able to produce a reply. Please try again or provide more detail."

        assistant_msg = MemoryMessage(
            role="assistant", content=[{"type": "text", "text": reply_text}]
        )
        self.memory.append_message(conversation_id, user_msg)
        self.memory.append_message(conversation_id, assistant_msg)
        if plan:
            plan_summary = reply_text or json.dumps(plan)
            self.memory.update_state(
                conversation_id,
                {"last_plan_summary": plan_summary},
            )
        log_event(
            conversation_id,
            "assistant_reply",
            {"reply": reply_text, "plan_keys": list(plan.keys())},
        )

        return {
            "conversation_id": conversation_id,
            "reply": reply_text,
            "plan": plan or None,
        }
