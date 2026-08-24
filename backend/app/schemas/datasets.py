from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MESSAGES = 5_000
MAX_EVALUATION_CASES = 200
MAX_CONTENT_CHARS = 20_000

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]
Content = Annotated[
    str,
    StringConstraints(strict=True, max_length=MAX_CONTENT_CHARS),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MessageImport(StrictSchema):
    id: Identifier
    role: Literal["user", "assistant", "system", "tool"]
    content: Content
    timestamp: datetime | None = None
    metadata: dict[str, JsonValue] | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be empty")
        return value


class ConversationImport(StrictSchema):
    id: Identifier
    messages: list[MessageImport] = Field(min_length=1)


class EvaluationCaseImport(StrictSchema):
    id: Identifier
    query: Content
    relevant_memory_ids: list[Identifier] = Field(min_length=1)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value

    @field_validator("relevant_memory_ids")
    @classmethod
    def relevant_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("relevant_memory_ids must not contain duplicates")
        return value


class DatasetImport(StrictSchema):
    schema_version: Literal["0.1"]
    name: Identifier
    conversations: list[ConversationImport] = Field(min_length=1)
    evaluation_cases: list[EvaluationCaseImport] = Field(
        default_factory=list,
        max_length=MAX_EVALUATION_CASES,
    )

    @model_validator(mode="after")
    def validate_dataset_references(self) -> "DatasetImport":
        conversation_ids: set[str] = set()
        memory_ids: set[str] = set()
        message_count = 0

        for conversation in self.conversations:
            if conversation.id in conversation_ids:
                raise ValueError(
                    f"duplicate conversation ID: {conversation.id}"
                )
            conversation_ids.add(conversation.id)

            for message in conversation.messages:
                message_count += 1
                if message.id in memory_ids:
                    raise ValueError(f"duplicate message ID: {message.id}")
                memory_ids.add(message.id)

        if message_count > MAX_MESSAGES:
            raise ValueError(
                f"dataset contains {message_count} messages; maximum is {MAX_MESSAGES}"
            )

        evaluation_case_ids: set[str] = set()
        for evaluation_case in self.evaluation_cases:
            if evaluation_case.id in evaluation_case_ids:
                raise ValueError(
                    f"duplicate evaluation case ID: {evaluation_case.id}"
                )
            evaluation_case_ids.add(evaluation_case.id)

            missing_ids = sorted(
                set(evaluation_case.relevant_memory_ids) - memory_ids
            )
            if missing_ids:
                raise ValueError(
                    "relevant_memory_ids reference missing memories: "
                    + ", ".join(missing_ids)
                )

        return self


class DatasetSummary(BaseModel):
    id: str
    schema_version: str
    name: str
    imported_at: datetime
    conversation_count: int
    memory_count: int
    evaluation_case_count: int


class DatasetListResponse(BaseModel):
    items: list[DatasetSummary]
    total: int


class MemoryResponse(BaseModel):
    id: str
    conversation_id: str
    position: int
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime | None
    metadata: dict[str, JsonValue] | None


class MemoryPageResponse(BaseModel):
    items: list[MemoryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
