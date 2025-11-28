import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic
from pydantic import ValidationError

from agent.logger import log_event
from agent.memory import InMemoryConversationMemory, MemoryMessage, to_claude_messages
from agent.prompts import STRUCTURED_SYSTEM_PROMPT, TOOL_SYSTEM_PROMPT
from models.schemas import (
    AccommodationRequest,
    BudgetRequest,
    BudgetResponse,
    ChatLLMResponse,
    Adjustments,
    DayNoteOverride,
    DayPlan,
    ElevationRequest,
    ElevationProfile,
    POIRequest,
    PointOfInterest,
    VisaRequest,
    VisaRequirement,
    RouteRequest,
    TripPlan,
    WeatherRequest,
)
from tools import accomodation, budget, elevation, poi, route, visa, weather


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
            "get_elevation_profile": elevation.get_elevation_profile,
            "get_points_of_interest": poi.get_points_of_interest,
            "check_visa_requirements": visa.check_visa_requirements,
            "estimate_budget": budget.estimate_budget,
        }
        self.tool_input_models: Dict[str, Any] = {
            "get_route": RouteRequest,
            "find_accommodation": AccommodationRequest,
            "get_weather": WeatherRequest,
            "get_elevation_profile": ElevationRequest,
            "get_points_of_interest": POIRequest,
            "check_visa_requirements": VisaRequest,
            "estimate_budget": BudgetRequest,
        }
        self.tool_specs = self._build_tool_specs()
        self.memory = InMemoryConversationMemory(max_messages=50)

    
    async def _emit_progress(self, cb: Optional[Callable[[Dict[str, Any]], Any]], payload: Dict[str, Any]) -> None:
        if not cb:
            return
        try:
            result = cb(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # Progress updates should never break core flow
            return

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

    def _apply_adjustments(self, trip_plan: TripPlan, adjustments: Adjustments) -> TripPlan:
        if not adjustments:
            return trip_plan

        if adjustments.note_overrides:
            override_map = {}
            for item in adjustments.note_overrides:
                if isinstance(item, DayNoteOverride):
                    override_map[item.day] = item.notes
                elif isinstance(item, dict) and "day" in item and "notes" in item:
                    override_map[item["day"]] = item["notes"]
            updated_itinerary: List[DayPlan] = []
            for day in trip_plan.itinerary:
                if day.day in override_map:
                    day.notes = override_map[day.day]
                updated_itinerary.append(day)
            trip_plan.itinerary = updated_itinerary

        if adjustments.target_days:
            target = adjustments.target_days
            current = trip_plan.days
            if target > current:
                last_end = trip_plan.itinerary[-1].end if trip_plan.itinerary else ""
                for idx in range(current + 1, target + 1):
                    trip_plan.itinerary.append(
                        DayPlan(
                            day=idx,
                            start=last_end,
                            end=last_end,
                            distance_km=0.0,
                            accommodation=None,
                            weather=None,
                            elevation=None,
                            points_of_interest=None,
                            visa=trip_plan.itinerary[0].visa if trip_plan.itinerary else None,
                            notes="Additional day added per adjustments.",
                        )
                    )
                trip_plan.days = target
            elif target < current:
                trip_plan.itinerary = trip_plan.itinerary[:target]
                trip_plan.days = target

        return trip_plan

    async def _build_trip_plan(self, plan: Dict[str, Any]) -> Optional[TripPlan]:
        """
        Build a normalized TripPlan from accumulated tool outputs to ensure the API
        returns a full itinerary even if the LLM structured parsing fails.
        """
        route_data = plan.get("get_route")
        if isinstance(route_data, list):
            route_data = route_data[0] if route_data else None
        if not isinstance(route_data, dict):
            return None

        segments = route_data.get("segments") or []
        accom_data = plan.get("find_accommodation")
        if accom_data is None:
            accom_data = []
        if not isinstance(accom_data, list):
            accom_data = [accom_data]
        accom_by_day = {item.get("day"): item.get("options") for item in accom_data if isinstance(item, dict)}

        weather_data = plan.get("get_weather")
        if weather_data is None:
            weather_data = []
        if not isinstance(weather_data, list):
            weather_data = [weather_data]
        weather_by_day = {}
        for item in weather_data:
            if isinstance(item, dict):
                daily = item.get("daily") or []
                for entry in daily:
                    day_idx = entry.get("day")
                    if day_idx is not None:
                        weather_by_day[day_idx] = entry

        elevation_data = plan.get("get_elevation_profile")
        if elevation_data is None:
            elevation_data = []
        if not isinstance(elevation_data, list):
            elevation_data = [elevation_data]
        elevation_by_day = {}
        for item in elevation_data:
            if isinstance(item, dict):
                profiles = item.get("profile") or []
                for entry in profiles:
                    day_idx = entry.get("day")
                    if day_idx is not None:
                        elevation_by_day[day_idx] = entry

        poi_data = plan.get("get_points_of_interest")
        if poi_data is None:
            poi_data = []
        if not isinstance(poi_data, list):
            poi_data = [poi_data]
        poi_by_day = {}
        for item in poi_data:
            if isinstance(item, dict):
                day_idx = item.get("day")
                if day_idx is not None:
                    poi_by_day[day_idx] = item.get("pois")

        visa_data = plan.get("check_visa_requirements")
        if isinstance(visa_data, dict):
            visa_req = visa_data.get("requirement")
        else:
            visa_req = None

        budget_data = plan.get("estimate_budget")
        budget_resp = budget_data if isinstance(budget_data, dict) else None

        itinerary: List[DayPlan] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            day_idx = seg.get("day")
            if day_idx is None:
                continue
            note_val = seg.get("notes")
            if not note_val:
                note_val = "Continue along secondary roads."
            itinerary.append(
                DayPlan(
                    day=day_idx,
                    start=seg.get("start", ""),
                    end=seg.get("end", ""),
                    distance_km=seg.get("distance_km", 0.0),
                    accommodation=accom_by_day.get(day_idx),
                    weather=weather_by_day.get(day_idx),
                    elevation=elevation_by_day.get(day_idx),
                    points_of_interest=poi_by_day.get(day_idx),
                    visa=visa_req,
                    notes=note_val,
                )
            )

        if not itinerary:
            return None

        if not budget_resp:
            try:
                budget_resp_model = await budget.estimate_budget(
                    BudgetRequest(days=route_data.get("days")),
                    itinerary=[day.model_dump() for day in itinerary],
                )
                budget_resp = budget_resp_model.model_dump()
            except Exception:
                budget_resp = None

        return TripPlan(
            total_distance_km=route_data.get("total_distance_km", 0.0),
            days=route_data.get("days", len(itinerary)),
            itinerary=sorted(itinerary, key=lambda d: d.day),
            budget=budget_resp,
        )

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
            {
                "name": "get_elevation_profile",
                "description": "Get terrain difficulty — elevation gain, elevation loss, and a simple difficulty rating for a given location/day. Use this to summarize hilliness or effort expectations for each trip day. Parameters: `location` and `day`. Mocked data; no live terrain API calls.",
                "input_schema": self._schema(ElevationRequest),
            },
            {
                "name": "get_points_of_interest",
                "description": "Provide nearby points of interest (landmarks, parks, museums, viewpoints, food) for a given location/day. Use this to enrich daily plans with suggested stops. Parameters: `location` and `day`. Mocked data only; no live API.",
                "input_schema": self._schema(POIRequest),
            },
            {
                "name": "check_visa_requirements",
                "description": "Check if a traveler needs a visa for the destination. Inputs: nationality, destination_country, optional stay_length_days. Outputs whether a visa is required, type, allowed stay days, and notes. Mocked data only; no live API.",
                "input_schema": self._schema(VisaRequest),
            },
            {
                "name": "estimate_budget",
                "description": "Estimate total and per-day budget for the trip based on days, lodging costs, food, and incidentals. Inputs: days (optional if itinerary is known), currency, nightly_budget, food_per_day, incidentals_per_day, travelers. Mocked data only; no live API.",
                "input_schema": self._schema(BudgetRequest),
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
            print("stop_reason:", resp.stop_reason)
            print("raw:", resp.content[0].text)
            print("parsed:", resp.parsed_output)
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

    def _build_initial_messages(
        self, conversation_id: str, user_message: str
    ) -> tuple[List[Dict[str, Any]], MemoryMessage]:
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
                    "content": [
                        {"type": "text", "text": f"Previous plan summary:\n{last_plan_summary}"}
                    ],
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
        return messages, user_msg

    async def _run_tool_loop(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        progress_cb: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any], Any, List[Dict[str, Any]]]:
        plan: Dict[str, Any] = {}
        tool_round = 0
        tool_calls: List[Dict[str, Any]] = []
        max_rounds = 4  # primary safeguard
        cleanup_rounds = 2  # limited retries to clear dangling tool_use
        total_rounds_allowed = max_rounds + cleanup_rounds
        last_response = await self._call_llm(
            messages=messages, tools=self.tool_specs, system=TOOL_SYSTEM_PROMPT
        )
        await self._emit_progress(progress_cb, {"stage": "llm_response_received"})

        while tool_round < total_rounds_allowed:
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
                await self._emit_progress(progress_cb, {"stage": "no_tool_calls"})
                break

            tool_round += 1
            tool_results_payload: List[Dict[str, Any]] = []
            for call in tool_calls:
                call_name = self._block_attr(call, "name")
                call_id = self._block_attr(call, "id")
                call_input = self._block_attr(call, "input") or {}
                if call_name:
                    await self._emit_progress(
                        progress_cb,
                        {"stage": "calling_tool", "tool": call_name, "id": call_id, "round": tool_round},
                    )
                if not call_name:
                    continue
                if not call_input:
                    error_msg = f"Missing required fields for {call_name}; skipping tool call."
                    log_event(
                        conversation_id,
                        "tool_input_missing",
                        {"name": call_name, "id": call_id},
                    )
                    tool_results_payload.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": [{"type": "text", "text": error_msg}],
                        }
                    )
                    await self._emit_progress(
                        progress_cb,
                        {"stage": "tool_result", "tool": call_name, "id": call_id, "ok": False, "reason": "missing_input"},
                    )
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
                    await self._emit_progress(
                        progress_cb,
                        {"stage": "tool_result", "tool": call_name, "id": call_id, "ok": False, "reason": "validation_error"},
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
                    await self._emit_progress(
                        progress_cb,
                        {"stage": "tool_result", "tool": call_name, "id": call_id, "ok": False, "reason": "execution_error"},
                    )
                    continue
                existing = plan.get(call_name)
                if isinstance(existing, list):
                    existing.append(output)
                    plan[call_name] = existing
                elif existing is not None:
                    plan[call_name] = [existing, output]
                else:
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
                await self._emit_progress(
                    progress_cb,
                    {"stage": "tool_result", "tool": call_name, "id": call_id, "ok": True},
                )

            messages.append({"role": "assistant", "content": last_response.content})
            messages.append({"role": "user", "content": tool_results_payload})
            last_response = await self._call_llm(
                messages=messages, tools=self.tool_specs, system=TOOL_SYSTEM_PROMPT
            )
            await self._emit_progress(progress_cb, {"stage": "llm_response_received"})

        # If we exhausted retries and still have dangling tool_use, strip them to avoid parser errors
        dangling_tool_use = [
            item for item in getattr(last_response, "content", []) if self._block_type(item) == "tool_use"
        ]
        if dangling_tool_use:
            log_event(
                conversation_id,
                "tool_calls_dangling_stripped",
                {"count": len(dangling_tool_use)},
            )
            cleaned = [
                item for item in last_response.content if self._block_type(item) != "tool_use"
            ]
            last_response.content = cleaned
            await self._emit_progress(progress_cb, {"stage": "dangling_tool_calls_stripped", "count": len(dangling_tool_use)})

        await self._emit_progress(progress_cb, {"stage": "tool_loop_complete", "rounds": tool_round})
        return messages, plan, last_response, tool_calls

    async def _finalize_response(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        last_response: Any,
        plan: Dict[str, Any],
        tool_calls: List[Dict[str, Any]],
        progress_cb: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> tuple[str, Dict[str, Any], Optional[List[str]], Optional[List[str]]]:
        # The structured call must NOT have a prefilled assistant turn last.
        # We pass the conversation up to the last user/tool_result message.
        await self._emit_progress(progress_cb, {"stage": "parsing_structured"})
        structured = await self._call_llm_structured(
            messages=messages, system=STRUCTURED_SYSTEM_PROMPT, conversation_id=conversation_id
        )

        print("Structured response:", structured)
        reply_text = ""
        questions: Optional[List[str]] = None
        tool_calls_structured: Optional[List[str]] = None
        trip_plan = await self._build_trip_plan(plan)
        if structured:
            reply_text = structured.reply or ""
            questions = structured.questions
            tool_calls_structured = structured.tool_calls
            adjustments = structured.adjustments
        else:
            fallback_text = "".join(
                [
                    self._block_attr(block, "text") or ""
                    for block in last_response.content
                    if self._block_type(block) == "text"
                ]
            ).strip()
            reply_text = fallback_text
            adjustments = None

        if trip_plan:
            if adjustments:
                trip_plan = self._apply_adjustments(trip_plan, adjustments)
            await self._emit_progress(
                progress_cb,
                {"stage": "assembling_trip_plan", "has_plan": True, "adjusted": bool(adjustments)},
            )
        else:
            await self._emit_progress(
                progress_cb,
                {"stage": "assembling_trip_plan", "has_plan": False},
            )

        if not trip_plan and not tool_calls and not questions:
            questions = [
                "What are your start and end locations?",
                "How many kilometers per day would you like to ride?",
                "What dates are you targeting?",
                "Any accommodation preferences or budget?",
                "Any weather conditions to avoid?",
            ]
            if not reply_text:
                reply_text = "I need a few details before planning. Please clarify."

        if not reply_text:
            if questions:
                reply_text = "Could you clarify a few points?"
            elif plan:
                reply_text = "Here is a plan, let me know if you want modifications :\n"
            else:
                reply_text = "I wasn't able to produce a reply. Please try again or provide more detail."

        return reply_text, trip_plan, questions, tool_calls_structured

    async def chat(
        self,
        conversation_id: str,
        user_message: str,
        progress_cb: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> dict:
        """
        Runs a full tool-enabled exchange with Anthropic: send the user
        message, execute any requested tools, and return the assistant reply
        plus the tool outputs used to form the plan.
        """
        await self._emit_progress(progress_cb, {"stage": "start"})
        messages, user_msg = self._build_initial_messages(conversation_id, user_message)
        messages, plan, last_response, tool_calls = await self._run_tool_loop(
            conversation_id, messages, progress_cb=progress_cb
        )


        reply_text, triplan, questions, tool_calls_structured = await self._finalize_response(
            conversation_id, messages, last_response, plan, tool_calls, progress_cb=progress_cb
        )

        assistant_msg = MemoryMessage(
            role="assistant", content=[{"type": "text", "text": reply_text}]
        )
        self.memory.append_message(conversation_id, user_msg)
        self.memory.append_message(conversation_id, assistant_msg)
        if triplan:
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
                "plan_keys": list((plan or {}).keys()),
                "questions": questions or [],
                "tool_calls_structured": tool_calls_structured or [],
            },
        )
        await self._emit_progress(
            progress_cb,
            {
                "stage": "complete",
                "reply": reply_text,
                "has_plan": bool(triplan),
                "has_questions": bool(questions),
            },
        )

        return {
            "conversation_id": conversation_id,
            "reply": reply_text,
            "triplan": triplan or None,
            "questions": questions,
            "tool_calls": tool_calls_structured,
        }
