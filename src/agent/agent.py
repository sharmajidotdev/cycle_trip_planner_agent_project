import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic
from pydantic import ValidationError

from agent.logger import log_event
from agent.memory import InMemoryConversationMemory, MemoryMessage, to_claude_messages
from agent.prompts import SYSTEM_PROMPT
from models.schemas import (
    AccommodationRequest,
    
    ChatLLMResponse,
    RouteRequest,
    
    WeatherRequest,
    
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
                "description": "Route planning tool that returns a realistic-looking multi-day cycling route based on a start location, end location, and desired daily distance. Use this when you need to break a trip into daily cycling segments with distances and brief notes; do not use it for walking, driving, or non-cycling contexts. Parameters: `start` and `end` define the trip endpoints; `daily_distance_km` sets target distance per day and influences how many days/segments are produced. Limitations: no turn-by-turn directions. It does not return elevation, surfaces, or safety constraints—only day-level segments with start/end and notes.",
                "input_schema": self._schema(RouteRequest),
            },
            {
                "name": "find_accommodation",
                "description": "Accommodation lookup tool that returns plausible lodging options near a segment end point for a given day. Use this when you need hostels/hotels/BnBs along the cycling route; do not use it for booking or payment. Parameters: `location` is the target area for the overnight stop; `day` is the trip day, which may influence availability. Limitations: prices are approximate; it does not return booking links or confirm actual rooms. Outputs include option name, price, type, availability, and notes (e.g., bike storage, breakfast).",
                "input_schema": self._schema(AccommodationRequest),
            },
            {
                "name": "get_weather",
                "description": "Weather forecast tool that returns plausible conditions for a given location and day. Use this to provide day-level outlooks (conditions, highs/lows, precipitation chance) for cycling plans. Parameters: `location` sets the area to forecast; `day` is the trip day index used to vary conditions. Limitations: no hourly breakdown, and no wind/elevation-specific effects; it returns only day-level summaries. Outputs include conditions, high/low temperatures, and an estimated precipitation chance.",
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
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        return await asyncio.to_thread(
            self.client.messages.create,
            model=model,
            max_tokens=512,
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"},
            system=system,
        )

    async def _call_llm_structured(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str],
        conversation_id: str,
    ) -> Optional[ChatLLMResponse]:
        if not self.client:
            raise RuntimeError("Anthropic client not configured")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        beta = os.getenv("ANTHROPIC_STRUCTURED_BETA", "structured-outputs-2025-11-13")
        try:
            resp = await asyncio.to_thread(
                self.client.beta.messages.parse,
                model=model,
                max_tokens=512,
                messages=messages,
                system=system,
                output_format=ChatLLMResponse,
                betas=[beta],
            )
            return resp.parsed_output
        except Exception as exc:
            log_event(
                conversation_id,
                "structured_parse_error",
                {"error": str(exc)},
            )
            return None

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
        # 1) Build context and user message
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
        
        messages.append({"role": user_msg.role, "content": user_msg.content})
        log_event(
            conversation_id,
            "user_message",
            {
                "message": user_message,
                "history_count": len(prior),
                "has_last_plan_summary": bool(last_plan_summary),
                
            },
        )

        # 2) Repeatedly call tools until the model stops requesting them (or max rounds reached)
        plan: Dict[str, Any] = {}
        tool_round = 0
        tool_calls: List[Dict[str, Any]] = []
        max_rounds = 4  # safeguard to avoid infinite loops
        last_response = await self._call_llm(
            messages=messages, tools=self.tool_specs, system=SYSTEM_PROMPT
        )

        while tool_round < max_rounds:
            tool_calls = [
                item for item in last_response.content if self._block_type(item) == "tool_use"
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

            if not tool_calls:
                break

            tool_round += 1
            tool_results_payload: List[Dict[str, Any]] = []
            for call in tool_calls:
                call_name = self._block_attr(call, "name")
                call_id = self._block_attr(call, "id")
                call_input = self._block_attr(call, "input") or {}
                if not call_name:
                    continue
                try:
                    output = await self._execute_tool({"name": call_name, "input": call_input})
                except ValidationError as exc:
                    error_msg = f"Validation failed for {call_name}: {exc}"
                    log_event(
                        conversation_id,
                        "tool_validation_error",
                        {"name": call_name, "id": call_id, "error": str(exc), "input": call_input},
                    )
                    tool_results_payload.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": [{"type": "text", "text": error_msg}],
                        }
                    )
                    continue
                except Exception as exc:  # catch-all to avoid crashing the loop
                    error_msg = f"Execution failed for {call_name}: {exc}"
                    log_event(
                        conversation_id,
                        "tool_execution_error",
                        {"name": call_name, "id": call_id, "error": str(exc), "input": call_input},
                    )
                    tool_results_payload.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": [{"type": "text", "text": error_msg}],
                        }
                    )
                    continue
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

            messages.append({"role": "assistant", "content": last_response.content})
            messages.append({"role": "user", "content": tool_results_payload})
            last_response = await self._call_llm(
                messages=messages, tools=self.tool_specs, system=SYSTEM_PROMPT
            )

        # 3) Build final message list for structured answer
        final_messages: List[Dict[str, Any]] = messages + [
            {"role": "assistant", "content": last_response.content}
        ]

        # 4) Try structured output
        structured = await self._call_llm_structured(
            messages=final_messages, system=SYSTEM_PROMPT, conversation_id=conversation_id
        )
        print("Structured output:", structured)
        
        # 5) Fallback plain text from last response (if no structured)
        reply_text = ""
        questions: Optional[List[str]] = None
        tool_calls_structured: Optional[List[str]] = None
        if structured:
            reply_text = structured.reply or ""
            if structured.plan:
                plan = structured.plan
            questions = structured.questions
            tool_calls_structured = structured.tool_calls
        else:
            fallback_text = "".join(
                [
                    self._block_attr(block, "text") or ""
                    for block in last_response.content
                    if self._block_type(block) == "text"
                ]
            ).strip()
            reply_text = fallback_text

        # 7) If nothing usable returned, synthesize clarifying qs
        if not plan and not tool_calls and not questions:
            questions = [
                "What are your start and end locations?",
                "How many kilometers per day would you like to ride?",
                "What dates are you targeting?",
                "Any accommodation preferences or budget?",
                "Any weather conditions to avoid?",
            ]
            if not reply_text:
                reply_text = "I need a few details before planning. Please clarify."

        # 8) Guarantee non-empty reply
        
        if not reply_text:
            if questions:
                reply_text = "Could you clarify a few points?"
            elif plan:
                reply_text = "Here is a plan, let me know if you want modifications :\n"
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
            {
                "reply": reply_text,
                "plan_keys": list(plan.keys()),
                "questions": questions or [],
                "tool_calls_structured": tool_calls_structured or [],
            },
        )

        return {
            "conversation_id": conversation_id,
            "reply": reply_text,
            "plan": plan or None,
            "questions": questions,
            "tool_calls": tool_calls_structured,
        }
