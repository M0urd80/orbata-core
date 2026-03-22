from typing import Any

from pydantic import BaseModel, Field, field_validator


class PlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: float = Field(default=0.0, ge=0, description="Billing amount; coerced from strings.")

    @field_validator("price", mode="before")
    @classmethod
    def coerce_price(cls, v: object) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, bool):
            raise ValueError("price must be a number")
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            if not s:
                return 0.0
            return float(s)
        raise ValueError("price must be a number")


class PlanOut(BaseModel):
    id: str
    name: str
    price: float
    created_at: str

    @classmethod
    def from_orm_row(cls, row: Any) -> "PlanOut":
        raw = row.price
        price_f = float(raw) if raw is not None else 0.0
        return cls(
            id=str(row.id),
            name=row.name,
            price=price_f,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
