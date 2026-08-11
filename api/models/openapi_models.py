from typing import Any

from pydantic import BaseModel, Field


class ReconciliationQuery(BaseModel):
    query: str = Field(..., examples=["Goethe"])
    type: str | None = Field(default=None, examples=["DifferentiatedPerson"])
    limit: int | None = Field(default=None, examples=[5])
    properties: list[dict[str, Any]] | None = None


class ReconciliationRequest(BaseModel):
    queries: dict[str, ReconciliationQuery]


class EntityType(BaseModel):
    id: str
    name: str
    broader: list[dict[str, Any]] | None = None


class ReconciliationCandidate(BaseModel):
    id: str
    name: str
    score: float | int
    match: bool
    type: list[EntityType] | None = None


class ReconciliationResponse(BaseModel):
    result: list[ReconciliationCandidate] | None = None


class ExtendProperty(BaseModel):
    id: str = Field(..., examples=["preferredName"])
    settings: dict[str, Any] | None = None


class ExtendRequest(BaseModel):
    ids: list[str] = Field(..., examples=[["118540238"]])
    properties: list[ExtendProperty]


class ExtendCellLiteral(BaseModel):
    str: str


class ExtendEntityValue(BaseModel):
    id: str
    name: str
    type: list[EntityType] | None = None


class ExtendResponse(BaseModel):
    meta: list[dict[str, Any]]
    rows: dict[str, dict[str, list[Any]]]


class SuggestResponseItem(BaseModel):
    id: str
    name: str
    type: list[EntityType] | None = None


class SuggestResponse(BaseModel):
    result: list[SuggestResponseItem]


class UpdateStatusResponse(BaseModel):
    last_oai_harvest: str | None = None
    last_successful_update: str | None = None
    last_failed_update: str | None = None
    last_error: str | None = None
    updates: dict[str, Any] | None = None
