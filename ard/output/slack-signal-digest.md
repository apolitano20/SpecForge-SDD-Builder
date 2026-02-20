# slack-signal-digest — Software Design Document

## Project Overview

A personal Slack digest tool that connects to multiple Slack workspaces, ingests messages from selected channels, summarizes threads, extracts actionable items based on user-defined interests, and presents them in a dashboard and optional daily/weekly digest. The system learns from user feedback to improve filtering and ranking over time.

## Tech Stack

- Python 3.12
- FastAPI
- SQLite
- React 18
- APScheduler
- SentenceTransformers

## Key Design Decisions

- Chose SQLite for persistent storage due to its simplicity and zero-config setup for local development.
- Implemented scheduled background ingestion using APScheduler for automated digest generation.
- Utilized SentenceTransformers for generating embeddings to enable semantic similarity-based ranking.
- Implemented in-memory embedding comparison for item ranking to avoid the complexity of a dedicated vector store.
- Centralized data access through the Database component to ensure consistent data access patterns.
- Implemented feedback mechanism to adjust interest profile weights, improving filtering over time.
- Used the Slack Web API for retrieving messages, as it is suitable for historical ingestion in a personal tool context.
- Deliver digests via email, requiring an SMTP configuration.

## Directory Structure

```
src/
  api/
    routes.py
  core/
    message_processor.py
    item_ranker.py
    digest_generator.py
  connectors/
    slack_connector.py
  models/
    user.py
    item.py
    feedback.py
  db/
    database.py

```

## Components

### SlackConnector

- **Type:** Subsystem
- **File:** `src/connectors/slack_connector.py`
- **Purpose:** Connects to Slack workspaces using the Slack Web API, retrieves messages from specified channels within a given time window, and handles authentication and authorization.
- **Dependencies:** Database

### MessageProcessor

- **Type:** Subsystem
- **File:** `src/core/message_processor.py`
- **Purpose:** Processes raw Slack messages, collapses threads into summaries, extracts actionable items, removes low-value chatter and duplicates, and applies the ignore list.
- **Dependencies:** Database

### ItemRanker

- **Type:** Subsystem
- **File:** `src/core/item_ranker.py`
- **Purpose:** Ranks extracted items by relevance and recency using semantic similarity based on the user's interest profile and generates embeddings for ranking.
- **Dependencies:** Database

### DigestGenerator

- **Type:** Subsystem
- **File:** `src/core/digest_generator.py`
- **Purpose:** Generates a daily or weekly digest of ranked items and delivers it to the user via email.
- **Dependencies:** Database

### Database

- **Type:** DataStore
- **File:** `src/db/database.py`
- **Purpose:** Provides persistent storage for Slack messages, extracted items, user profiles, ignore lists, and feedback data using SQLite.

### Scheduler

- **Type:** Utility
- **File:** `src/core/scheduler.py`
- **Purpose:** Schedules periodic ingestion of Slack messages and generation of digests using APScheduler.
- **Dependencies:** SlackConnector, MessageProcessor, ItemRanker, DigestGenerator

### API

- **Type:** API
- **File:** `src/api/routes.py`
- **Purpose:** Exposes REST endpoints for managing Slack connections, viewing the dashboard, providing feedback, and configuring user profiles.
- **Dependencies:** SlackConnector, MessageProcessor, ItemRanker, DigestGenerator, Database

### UIComponent

- **Type:** UIComponent
- **File:** `src/ui/dashboard.jsx`
- **Purpose:** Provides a user interface for viewing the digest, managing Slack connections, and providing feedback.
- **Dependencies:** API

## Data Models

### User

Represents a user of the system, storing their Slack workspace connections, selected channels, interest profile, and ignore list.

**Key fields:**

- interest_profile: JSONB
- ignore_list: JSONB

### Item

Represents an extracted item from a Slack message, including its summary, category, relevance score, and a deep link to the original message.

**Key fields:**

- category: enum
- relevance_score: float
- embedding: BLOB

### Feedback

Represents user feedback on an extracted item, used to improve filtering and ranking over time.

**Key fields:**

- item_id: FK:Item.id
- signal: enum(relevant, not_relevant)
- timestamp: datetime

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/slack` | Authenticates a user with Slack and adds a new workspace connection. |
| `GET` | `/api/workspaces` | Lists the user's connected Slack workspaces. |
| `POST` | `/api/workspaces/{workspace_id}/channels` | Selects channels for a given workspace to include in the digest. |
| `GET` | `/api/digest` | Retrieves the latest digest for the user. |
| `POST` | `/api/items/{item_id}/feedback` | Submits feedback on an extracted item. |
| `GET` | `/api/profile` | Retrieves the user's profile and settings. |
| `PUT` | `/api/profile` | Updates the user's profile and settings (interest profile, ignore list). |

### `POST /api/auth/slack`

Authenticates a user with Slack and adds a new workspace connection.

### `GET /api/workspaces`

Lists the user's connected Slack workspaces.

### `POST /api/workspaces/{workspace_id}/channels`

Selects channels for a given workspace to include in the digest.

### `GET /api/digest`

Retrieves the latest digest for the user.

### `POST /api/items/{item_id}/feedback`

Submits feedback on an extracted item.

### `GET /api/profile`

Retrieves the user's profile and settings.

### `PUT /api/profile`

Updates the user's profile and settings (interest profile, ignore list).

---

## Reviewer Notes (Minor)

The following minor suggestions were noted but did not block verification:

- **[completeness]** The tech stack lists no LLM or NLP library for thread summarization and actionable item extraction, which are core features. SentenceTransformers handles embeddings/ranking but not generative summarization. The coding agent will need to infer whether to use a local model (e.g., via Ollama/llama.cpp) or an API-based LLM (e.g., OpenAI). This is a significant implementation decision left implicit.
- **[completeness]** The email delivery mechanism for DigestGenerator is mentioned in key_decisions but no SMTP library (e.g., smtplib, sendgrid) appears in the tech stack, and there is no data model or config entity for SMTP/email settings. The coding agent can infer this, but it is a notable gap for a named feature.
- **[completeness]** There is no data model for WorkspaceConnection or Channel, which are persistent entities needed to store Slack OAuth tokens, workspace IDs, and selected channels per user. The User model's JSONB fields could absorb this, but explicit models would make the design clearer and more robust for multi-workspace support.
- **[completeness]** The feedback loop mechanism (how Feedback signals adjust interest profile weights over time) is described in key_decisions but has no corresponding component or endpoint. There is no retraining/recalibration component, and the API has no endpoint to trigger or inspect the feedback-driven profile update. The coding agent can embed this logic in ItemRanker or a utility, but the data flow is untraced.
- **[completeness]** The ignore list feature (channels/users/patterns) is referenced in the User model and MessageProcessor but there is no API endpoint to manage the ignore list independently (add/remove entries). The PUT /api/profile endpoint could cover this, but a dedicated endpoint would make the feature more discoverable.
- **[consistency]** The Scheduler component is listed in components with file_path src/core/scheduler.py, but this file does not appear in the directory_structure. This is a minor inconsistency the coding agent will resolve automatically.
- **[consistency]** The UIComponent file_path is src/ui/dashboard.jsx, but the directory_structure does not include a ui/ directory. The coding agent will create it, but the omission is inconsistent.
- **[ambiguity]** The configurable time window (e.g., last 7/30 days) for ingestion is mentioned in the project description but it is unclear whether this is a global setting, per-workspace, or per-channel configuration. The User model's JSONB fields could hold this, but the data flow for how the Scheduler passes this window to SlackConnector is unspecified.
- **[completeness]** No observability or structured logging component is defined. The design_rationale acknowledges this and defers it to the coding agent, which is acceptable for a personal tool, but at minimum a logging configuration module would be beneficial.

---

## User Design Decisions

The following design choices were made by the user during the review process:

- **Challenge #4** (The feedback mechanism ('relevant / not relevant') is described as improving filtering over time, but there is no component or data model that closes this loop. The Feedback data is submitted via POST /api/items/{item_id}/feedback but nothing reads it back to adjust MessageProcessor or ItemRanker behavior. The architecture must clarify how feedback actually influences future filtering — otherwise the feature is a dead end.): Feedback adjusts interest profile weights *(selected option)*
