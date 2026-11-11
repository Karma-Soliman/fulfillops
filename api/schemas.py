
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class OrderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: Literal["KIT-100", "PART-200", "PACK-300"]
    quantity: StrictInt = Field(ge=1, le=20)


class OrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: StrictStr = Field(min_length=1, max_length=64)
    items: list[OrderItemRequest] = Field(min_length=1, max_length=10)
