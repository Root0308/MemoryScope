from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(tags=["system"])


class DatabaseHealth(BaseModel):
    engine: Literal["sqlite"]
    status: Literal["configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["memoryscope-api"]
    version: str
    database: DatabaseHealth


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="memoryscope-api",
        version="0.1.0",
        database=DatabaseHealth(engine="sqlite", status="configured"),
    )
