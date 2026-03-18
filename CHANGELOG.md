# Changelog

All notable changes to the SynApps project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — v1.0.0-alpha

### Added

- **N-26: Workflow Variables + Environment Secrets** — `WorkflowVariableStore` (per-flow key-value, `{{var.name}}` template substitution in node data fields). `WorkflowSecretStore` (Fernet-encrypted at rest, `{{secret.name}}` substitution, values masked as `***` in API responses). `_resolve_template` / `_resolve_node_data` / `_mask_secrets` helpers. 4 REST endpoints: `GET/PUT /api/v1/workflows/{id}/variables`, `GET/PUT /api/v1/workflows/{id}/secrets`. Secret values masked in all execution log entries. 40 tests.
- **N-25: Execution Logs + Debug Console** — `ExecutionLogStore` singleton (thread-safe, in-memory, append-only). Emits 5 event types per node lifecycle: `node_start`, `node_retry`, `node_success`, `node_fallback`, `node_error` — each carrying timestamp, run_id, node_id, node_type, attempt, input, output, error, duration_ms. `GET /api/v1/executions/{run_id}/logs` returns `{run_id, count, logs[]}` (404 if no logs). `POST /flows/{id}/runs?debug=true` polls until terminal and returns logs inline with status. 19 tests.
- **N-24: Execution Analytics** — `AnalyticsService` (stateless, no migration needed). `GET /api/v1/analytics/workflows`: per-flow `run_count`, `success_rate`, `error_rate`, `avg_duration_seconds`, `last_run_at`. `GET /api/v1/analytics/nodes`: per-node `execution_count`, `success_rate`, `avg_duration_seconds`. Both support optional `flow_id` filter. No auth required (read-only). 25 tests.
- **N-23: Workflow Marketplace API** — `MarketplaceRegistry` (separate from `TemplateRegistry`; tracks `install_count` + `featured`). `POST /api/v1/marketplace/publish` (auth, scrubs credentials, 404 on missing flow), `GET /marketplace/search` (paginated, q/category/tags filters), `GET /marketplace/featured` (top 10 by install_count), `POST /marketplace/install/{id}` (auth, re-maps all IDs, increments install_count). 33 tests.
- **N-22: Error Handling + Retry Logic + Workflow Versioning** — `ErrorHandlerNodeApplet` (`error_handler` type): `fallback_content` (output substitution on error), `suppress_error` (continue pipeline silently). `DeadLetterQueue` singleton: auto-populated by `_fail()`, 4 REST endpoints (`GET/GET/{id}/DELETE/{id}/POST/{id}/replay /api/v1/dlq`). `retry_on` conditions in node `retry_config`: `"all"`, `"timeout"`, `"error"`, or list — skip retries that don't match. `FlowVersionRegistry`: snapshots on `PUT /flows/{id}`, sequential version numbers. `PUT /flows/{id}` endpoint (create-or-update). Rollback (`POST /flows/{id}/rollback`) is reversible — snapshots before restoring. Diff (`GET /flows/{id}/diff`) computes `nodes_added/removed/changed`, `edges_added/removed`, supports `"current"` keyword. Frontend: orange ⚠️ error_handler node in canvas, palette entry, config modal. 76 new tests (41 + 35).
- **N-20: Scheduler Node** — cron-triggered workflows. `SchedulerNodeApplet` (passthrough trigger), `SchedulerService` async background tick loop (30s default, `SCHEDULER_TICK_SECONDS` env var), `SchedulerRegistry` (thread-safe in-memory, `croniter`-powered next-run computation). 5 REST endpoints: `POST /api/v1/schedules`, `GET /api/v1/schedules`, `GET /api/v1/schedules/{id}`, `PATCH /api/v1/schedules/{id}` (pause/resume/rename/recron), `DELETE /api/v1/schedules/{id}`. Frontend: ⏰ green node in canvas, config modal, palette entry.
- **N-21: Template Marketplace Enhancements** — credential scrubbing on export (`_scrub_node_credentials` blanks 18 credential field variants), `GET /api/v1/templates/search` endpoint (q/tags/category AND-combined filters). Complements existing N-17 versioned registry + publish/instantiate.
- **Docs: Getting Started Guide** — `docs/getting-started.md` with Docker Quick Start, local dev setup, first workflow tutorial, and env vars reference.
- **N-19: Webhook Trigger Node** — inbound webhook trigger that starts a workflow when a unique URL receives a POST request. Includes `WebhookTriggerRegistry` (in-memory, thread-safe, Fernet-encrypted secrets), HMAC-SHA256 signature verification (`X-Webhook-Signature: sha256=<hex>`), and 5 REST endpoints: `POST /api/v1/webhook-triggers`, `GET /api/v1/webhook-triggers`, `GET /api/v1/webhook-triggers/{id}`, `DELETE /api/v1/webhook-triggers/{id}`, `POST /api/v1/webhook-triggers/{id}/receive`. Frontend: purple color variant in node canvas, config panel, palette entry.
- **N-18: HTTP Request Node** — universal API connector supporting GET/POST/PUT/PATCH/DELETE, bearer/basic/API-key auth, SSRF protection (private IP ranges blocked), configurable retry with exponential backoff, response header capture, Jinja2 template rendering for URL/headers/body.
- **N-17: Workflow Export/Import + UX Polish** — export flows as JSON/YAML, import into gallery, template marketplace with versioning (semver), collision-free re-import.
- **N-15: Comprehensive Test Suite** — 1,566 total tests (1,457 backend + 109 frontend + 4 E2E). CRUCIBLE-gated test quality (Gate 2 non-empty assertions, Gate 5 silent exception audit, Gate 8 coverage integrity).
- **N-13: Code Node with Sandboxing** — execute arbitrary Python/JavaScript with restricted builtins, timeout, and filesystem isolation.
- **N-11: Conditional Routing (If/Else)** — expression-based branching node.
- **N-10: Parallel Execution Engine** — fan-out/fan-in with configurable concurrency, `ForEach` node for collection iteration.
- **N-09: Universal LLM Node** — provider-agnostic (OpenAI, Anthropic, Google, Ollama, Custom) with streaming support.
- **N-12: JWT Authentication** — JWT with refresh tokens, API key management, encrypted keys at rest (Fernet), rate limiting per-user.

### Changed

- **Stack upgrade (N-07/N-08)** — Python 3.9 → 3.13, FastAPI 0.68 → 0.115, Pydantic v1 → v2, SQLAlchemy 1.x → 2.0 (async), frontend CRA → Vite 6, Tailwind 3 → 4, Zustand added, TypeScript strict mode.
- **CI/CD** — GitHub Actions pipeline with backend lint (Ruff), frontend lint (ESLint 9), type-check, backend tests with coverage (pytest-cov XML → Codecov), frontend tests (Vitest lcov → Codecov), OpenAPI spec freshness gate, Docker build gate.
- **Coverage config (CRUCIBLE Gate 8)** — `[tool.coverage.run] omit` added to `pyproject.toml` to exclude `tests/`, `venv/`, `migrations/`, `setup.py` from coverage measurement, eliminating ~8pp inflation.

### Fixed

- Aiosqlite teardown race in async tests (poll-until-terminal pattern).
- Ruff UP042 compliance — `(str, Enum)` → `StrEnum`.
- CI coverage path (`--cov=.` from `apps/orchestrator/` working-directory, not `--cov=apps/orchestrator`).

---

## [0.5.2] - 2025-06-10

### Added

- **Workflow Editor Enhancements**
  - Added node deletion functionality via keyboard (Delete key) and context menu
  - Implemented proper cleanup of connected edges when deleting nodes
  - Added enhanced context menu for workflow nodes with the following features:
    - Direct access to node configuration
    - Improved positioning next to nodes
    - Better styling with icons and dividers

## [0.5.1] - 2025-06-09

### Fixed

- **Workflow History Page**
  - Fixed run selection to show the latest workflow run by default instead of the oldest run
  - Ensured proper sorting of workflow runs by timestamp

## [0.5.0] - 2025-06-08

### Added

- **Node-Specific Configuration**
  - Implemented `NodeConfig` component for node-specific input configuration
  - Added configuration panels for Start, Writer, and Artist nodes:
    - **Start Node**: Input text area for initial workflow input data with JSON parsing
    - **Writer Node**: System prompt text area for configuring language model prompts
    - **Artist Node**: System prompt text area and generator selection dropdown
  - Added gear icon toggle button to open/close node configuration panels

- **Dynamic Workflow Execution Feedback**
  - Added status indicators (colored dots) in the upper-right corner of each node
  - Implemented progressive lighting of status indicators as workflow steps complete
  - Added visual feedback for running, success, and error states with appropriate colors
  - Enhanced node border styling to reflect execution status
  - Added backend tracking of completed workflow nodes via database
  - Implemented real-time WebSocket broadcasting of node completion status

### Changed

- **Workflow Editor UI**
  - Removed global Input Data Panel in favor of node-specific configurations
  - Updated CSS styling for better layout and consistency
  
- **Orchestrator Backend**
  - Enhanced `_execute_flow_async` to handle node-specific configuration data
  - Updated flow execution to use Start node's input data configuration
  - Added support for passing node-specific metadata (system prompts, generator selection) to applets
  - Added tracking of completed nodes during workflow execution
  - Created database migration for storing completed nodes in workflow runs
  - Enhanced WebSocket status updates to include completed nodes information

## [0.4.0] - 2025-06-07

### Added

- **Enhanced Run History Page**
  - Added workflow names to the Run History page for better identification
  - Implemented sorting functionality with newest-first as default
  - Added toggle button to switch between newest-first and oldest-first sorting
  - Improved UI styling for better readability

### Changed

- **FastAPI Modernization**
  - Replaced deprecated lifecycle event handlers (`@app.on_event`) with the modern lifespan context manager
  - Created a helper function `model_to_dict` to abstract Pydantic model serialization differences
  - Updated all Pydantic model dictionary conversions for compatibility with both v1 and v2
  - Fixed dependency injection in the Orchestrator class

## [0.3.0] - 2025-06-06

### Added

- **Database Persistence**
  - Implemented SQLAlchemy async ORM for database operations
  - Created models for flows, nodes, edges, and workflow runs
  - Added Alembic migrations for database schema management
  - Implemented repository pattern for data access

### Fixed

- **Workflow Execution Issues**
  - Consolidated duplicate `Orchestrator` class definitions
  - Fixed inconsistent handling of Pydantic models vs dictionaries
  - Ensured proper dictionary access for status objects
  - Fixed the `load_applet` method to properly load applet modules

- **Async Function Handling**
  - Properly awaited coroutines for database initialization and connection closing
  - Fixed async patterns in workflow execution
  - Improved error handling during async operations

## [0.2.0] - 2025-05-31

### Fixed

- **Workflow Editor Infinite Update Loop**
  - Modified the `handleNodeClick` function in `EditorPage.tsx` to check if the node already exists in the workflow
  - Used `useRef` to track previous flow values in `WorkflowCanvas.tsx` to prevent unnecessary re-renders
  - Implemented proper state comparison using JSON stringification in the `handleFlowChange` function

- **Node Panel Not Displaying**
  - Restructured the editor sidebar layout in `EditorPage.tsx` to properly display all panels
  - Added scrolling to the sidebar in `EditorPage.css` to ensure all content is accessible
  - Removed duplicate node panel code from the bottom of the component

- **Drag and Drop Not Working**
  - Implemented proper `onDrop` and `onDragOver` handlers in the `WorkflowCanvas` component
  - Fixed the `handleNodeClick` function to properly add new nodes when clicked
  - Added proper TypeScript type checking to prevent null reference errors

### Added

- **Enhanced Sidebar Layout**
  - Improved organization of the sidebar with Input Panel, Available Nodes, and Results Panel
  - Added overflow scrolling to ensure all panels are accessible

### Changed

- **Node Addition Logic**
  - Modified how nodes are added to the workflow when clicked vs. dragged
  - Ensured proper flow state updates when adding new nodes

## [0.1.0] - 2025-05-22

### Added

- **Initial MVP Release**
  - Basic workflow editor with React Flow
  - Support for Writer, Artist, and Memory applets
  - Real-time workflow execution via WebSockets
  - Results panel with text and image output support

### Fixed

- **Image Results Rendering**
  - Implemented a recursive scanning algorithm to detect image data in various formats
  - Added support for multiple image formats (URLs, base64, nested objects)

- **WebSocket Connection Issues**
  - Updated WebSocket URL to explicitly use `localhost:8000`
  - Added better connection management and logging
  - Implemented proper subscription in the EditorPage component
