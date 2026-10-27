"""Pydantic schema for the Architect's SDD draft.

Used as the OpenAI strict structured-output schema, so every field is required
(no defaults) and extra keys are forbidden. Fields that used to be optional in
the prompt-only format (file_path, protocol, dependencies) are now required but
may be empty. Field descriptions are sent to the model as part of the schema.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Component(BaseModel):
    """A building block of the system."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="PascalCase component name.")
    type: Literal["Subsystem", "DataStore", "Agent", "API", "UIComponent", "Utility"]
    purpose: str = Field(description="What this component does.")
    file_path: str = Field(description="Relative path where the component lives, e.g. src/services/auth.py.")
    dependencies: list[str] = Field(
        description="Names of other components this one depends on (component names only, never tech-stack items)."
    )


class DataModel(BaseModel):
    """A persistent entity."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="PascalCase entity name, e.g. User, Task.")
    purpose: str = Field(description="What this entity represents and why it exists.")
    key_fields: list[str] = Field(
        description=(
            "ONLY fields that represent design choices: foreign keys (user_id: FK:User.id), "
            "non-obvious types (status: enum(active,archived)), and fields that encode "
            "relationships or constraints. Never list obvious fields like id, name, created_at."
        )
    )


class ApiEndpoint(BaseModel):
    """A primary route of the API surface."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str = Field(description="Route path, e.g. /api/tasks.")
    description: str = Field(description="What the endpoint does and which component handles it.")


class ExternalActor(BaseModel):
    """An entity outside the system boundary."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="e.g. EndUser, PaymentGateway.")
    type: Literal["user", "system", "service"]
    description: str = Field(description="Role and interaction with the system.")


class InformationFlow(BaseModel):
    """A data exchange between actors and components."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from", description="Source actor or component name.")
    to: str = Field(description="Destination actor or component name.")
    data: str = Field(description="What data is exchanged, e.g. 'authentication credentials'.")
    protocol: str = Field(
        description="Architectural communication pattern, e.g. 'HTTP API'. Empty string if not applicable."
    )


class Context(BaseModel):
    """The context viewpoint: boundary, actors and flows."""

    model_config = ConfigDict(extra="forbid")

    system_boundary: str = Field(description="What the system IS and is NOT responsible for.")
    external_actors: list[ExternalActor]
    information_flows: list[InformationFlow]


class GlossaryEntry(BaseModel):
    """A domain-specific term."""

    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str = Field(description="1-2 sentence definition.")


class SDD(BaseModel):
    """The complete Software Design Document draft produced by the Architect."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(description="kebab-case, e.g. todo-rest-api.")
    project_description: str = Field(
        description="2-3 sentence summary of what the product does and why, written for a developer who will build it."
    )
    tech_stack: list[str] = Field(description="Specific frameworks/libraries, e.g. Python 3.12, FastAPI, SQLite.")
    directory_structure: str = Field(
        description="High-level tree of main directories and key files, as an indented text tree."
    )
    components: list[Component]
    data_models: list[DataModel]
    api_endpoints: list[ApiEndpoint]
    context: Context
    glossary: list[GlossaryEntry] = Field(description="Domain-specific terms only. Empty list is fine.")
    key_decisions: list[str] = Field(
        description="3-8 concise architectural decisions with their rationale. Rewritten from scratch each iteration."
    )
    design_rationale: str = Field(
        description=(
            "Internal field: address each challenge from the most recent reviewer response by index. "
            "Excluded from the final output."
        )
    )
