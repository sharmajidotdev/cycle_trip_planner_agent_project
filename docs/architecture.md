# Cycle Planner Architecture

## Overview
- **Purpose:** Tool-aware cycling trip planner that orchestrates Anthropic's Messages API with a suite of mocked/low-cost tools to produce day-by-day itineraries.
- **Entry point:** FastAPI service at `src/api/main.py` exposes `POST /chat`, wiring requests into `CyclingTripAgent`.
- **Key behaviors:** Gathers user requirements, calls tools when inputs are sufficient, reconciles results into a normalized `TripPlan`, and returns a concise reply plus structured plan data.

## Components
- **API layer (`src/api/main.py`):** FastAPI app that loads environment variables, initializes the Anthropic client (if `ANTHROPIC_API_KEY` is set), and forwards chat requests to the agent.
- **Agent core (`src/agent/agent.py`):** Coordinates message construction, tool invocation, error handling, plan assembly, and memory updates. It normalizes tool outputs into `TripPlan` objects and supports structured output parsing.
- **Prompts (`src/agent/prompts.py`):** System prompts defining tool-use rules and structured output contract.
- **Conversation memory (`src/agent/memory.py`):** Simple in-process store that caps history and tracks lightweight per-conversation state (`last_plan_summary`).
- **Logging (`src/agent/logger.py`):** Appends structured JSON log lines to `agent.log` or `AGENT_LOG_PATH`.
- **Models (`src/models/schemas.py`):** Pydantic schemas for tool inputs/outputs and chat responses (e.g., `RouteRequest`, `TripPlan`, `ChatLLMResponse`).
- **Tools (`src/tools/*`):** Small async helpers for route planning, accommodation, weather, elevation, POIs, visa checks, and budget estimation. External lookups try free/open APIs first, then fall back to deterministic mocks to keep responses stable.

## External Dependencies and Fallbacks
- **Anthropic:** Used for both tool-use and structured parsing (`ANTHROPIC_API_KEY` required). Optional overrides: `ANTHROPIC_MODEL`, `ANTHROPIC_STRUCTURED_BETA`.
- **Open-Meteo APIs:** Geocoding, reverse geocoding, and daily forecasts (weather). All fail soft and revert to mocked data.
- **OSRM Routing:** Attempts to split cycling routes into day stops using OSRM's free endpoint; falls back to generated segments on any error.
- **Overpass API:** Queries lodging POIs near a stop; falls back to generated accommodation options on error.
- **Fully mocked tools:** Elevation, POIs, visa checks, and budget estimation do not call external services.
- **Dependencies:** Pinned in `requirements.txt`; install with `pip install -r requirements.txt` inside a virtual environment.

## Data Flow Snapshot
1) Client `POST /chat` with `conversation_id` and `message`.
2) Agent builds the message stack from prior memory and current user input.
3) Anthropic model runs with tool specs; returned `tool_use` blocks are executed against local tools.
4) Tool outputs are aggregated and sent back through the model for a final response (tool loop with safeguards).
5) Structured output is parsed; `TripPlan` is assembled and adjusted if needed; memory and logs are updated.
6) API returns `reply`, optional `triplan`, clarifying `questions`, and `tool_calls` metadata.

## Safeguards
- Tool loop caps primary rounds (4) with limited cleanup retries to avoid runaway calls.
- Validation errors from Pydantic inputs are logged and surfaced to the model as tool results.
- Dangling tool calls are stripped before structured parsing to prevent parser errors.
