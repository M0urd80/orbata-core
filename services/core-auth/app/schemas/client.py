from typing import Optional

from pydantic import BaseModel


class ClientCreateRequest(BaseModel):
    name: str
    email_from_name: Optional[str] = None


class ClientCreateResponse(BaseModel):
    client_id: str
    api_key: str
