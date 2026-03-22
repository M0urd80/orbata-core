from typing import Optional

from pydantic import BaseModel, Field


class CreateClientRequest(BaseModel):
    """JSON body for ``POST /admin/clients`` (not query params)."""

    name: str
    email_from_name: Optional[str] = None
    plan_id: Optional[str] = Field(
        default=None,
        description="Plan UUID; omit to use the plan named Free",
    )


ClientCreateRequest = CreateClientRequest  # backward-compatible alias


class ClientCreateResponse(BaseModel):
    client_id: str
    api_key: str
