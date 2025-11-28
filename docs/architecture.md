## Core Shape
- Single FastAPI app (`src/api/main.py`) exposes one POST `/chat` endpoint that forwards validated requests into the agent and returns the reply, optional `TripPlan`, clarifying questions, and tool call hints.
- All shared data contracts live in `src/models/schemas.py` (chat payloads, itinerary pieces, tool inputs/outputs), so tools and the API reuse the same Pydantic models.
- Docker-first: `Dockerfile` builds a uvicorn container (requires `ANTHROPIC_API_KEY` at build time); `docker-compose.yml` wires env, port 8000, and restart policy.

## Agent Workflow (Two-Shot)
- The agent runs a two-pass loop: first pass drives tool use with `TOOL_SYSTEM_PROMPT`, executing any requested tools and feeding back `tool_result` blocks; second pass replays the conversation (minus the last assistant turn) with `STRUCTURED_SYSTEM_PROMPT` to parse a concise, structured `ChatLLMResponse`.
- Tool specs are derived from the Pydantic input models, so LLM tool calls are schema-aligned.
- A fallback trip plan assembler reconstructs a `TripPlan` from gathered tool outputs and will fabricate a safe reply/questions if parsing fails or tools return nothing.

## Memory and Logging
- Each process keeps per-conversation memory in `InMemoryConversationMemory`, storing every user/assistant message (and tool results) in Claude Messages format via `MemoryMessage` and `to_claude_messages`.
- State such as the last plan summary is also cached per conversation to influence future turns.
- A lightweight logger (`src/agent/logger.py`) appends JSONL events to `agent.log` (path configurable via `AGENT_LOG_PATH`), capturing user messages, tool calls/results, parse errors, and replies.

## Tooling Surface
- External-first tools: route planning uses OSRM with geocoding fallbacks (`src/tools/route.py`), weather uses Open-Meteo (`src/tools/weather.py`), and accommodation search hits Overpass/OSM (`src/tools/accomodation.py`), each falling back to deterministic mocks for stability. Budget estimation is an in-process mock that derives costs from itinerary/context.
- Mock-only tools: elevation profile (`src/tools/elevation.py`), points of interest (`src/tools/poi.py`), and visa requirements (`src/tools/visa.py`) return deterministic sample data to keep responses stable offline.
- Tool errors/validation issues are returned to the model as tool results, and dangling `tool_use` blocks are stripped before structured parsing to avoid failures.

## Resilience and Fallbacks
- If the structured LLM parse fails, the agent falls back to concatenated text from the last assistant turn and still attempts to return clarifying questions.
- When no plan can be built, the agent seeds default clarifying questions (start/end, distances, dates, lodging, weather constraints) to unblock the next turn.
