## Cycle Planner

Tool-aware cycling trip planner that uses Anthropic's Messages API plus a suite of lightweight tools to return day-by-day itineraries, budgets, and clarifying questions. External lookups (routing, geocoding, weather, lodging) fall back to deterministic mocks so plans remain stable even without network access.

### How to run locally
1. Ensure Python 3.11+ is available.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies from the pinned set:
   ```bash
   pip install -r requirements.txt
   ```
4. Set environment variables:
   - Copy `.env.example` to `.env` and fill values, or export manually.
   - `ANTHROPIC_API_KEY` (required for live LLM calls)
   - Optional: `ANTHROPIC_MODEL`, `ANTHROPIC_STRUCTURED_BETA`, `AGENT_LOG_PATH`
5. Start the API server:
   ```bash
   uvicorn src.api.main:app --reload
   ```
6. Send a request:
   ```bash
   curl -X POST http://127.0.0.1:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"conversation_id":"demo-1","message":"Plan a 3-day ride from Lyon to Grenoble at 70 km per day"}'
   ```

### Run with Docker Compose
1. Copy `.env.example` to `.env` and fill in your values.
   - `ANTHROPIC_API_KEY` is required at build time; `docker compose` forwards it as a build arg.
2. Build and start:
   ```bash
   docker compose up --build
   ```
3. The API will be available at `http://localhost:8000`.

### Streaming (Server-Sent Events)
- Endpoint: `GET /chat/stream?conversation_id=<id>&message=<text>`
- Returns `text/event-stream` with progress events (tool calls, assembly) and a final `stage: done` payload containing the reply and plan (when available).
- Example (CLI): `curl -N "http://localhost:8000/chat/stream?conversation_id=demo&message=Plan%20a%203-day%20ride%20from%20Lyon%20to%20Grenoble"`

### Frontend (SSE tester)
- A simple UI lives in `frontend/index.html`. Open it in a browser (or serve via `python -m http.server` from the `frontend` directory) and point it at your API base URL (defaults to `http://localhost:8000`). It streams `/chat/stream` events and logs them in-page.

### Documentation
- Architecture: `docs/architecture.md`
- Flow of code: `docs/flow-of-code.md`
- Example prompts: `docs/example-prompts.md`
