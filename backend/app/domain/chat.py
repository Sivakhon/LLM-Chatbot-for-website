"""Chat request/response contracts."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.product import Gender, Product, ProductType


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ProductFilters(BaseModel):
    gender: Gender | None = None
    product_types: list[ProductType] | None = Field(
        default=None, description="tops / bottoms / footwear / accessories"
    )
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_range(self) -> "ProductFilters":
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must be <= max_price")
        return self


class ChatRequest(BaseModel):
    """Stateless chat: the client sends the conversation so far.

    Keeping the server stateless makes it trivially horizontally scalable;
    the last message must come from the user.
    """

    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    filters: ProductFilters = Field(default_factory=ProductFilters)

    @model_validator(mode="after")
    def _last_message_from_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must have role 'user'")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "messages": [
                        {"role": "user", "content": "Black slim jeans for men under 1500 baht?"}
                    ],
                    "filters": {"gender": "men", "max_price": 1500},
                }
            ]
        }
    }


class ScoredProduct(BaseModel):
    product: Product
    score: float = Field(description="Cosine similarity in [0, 1]; higher is more relevant")


class ChatResponse(BaseModel):
    answer: str
    sources: list[ScoredProduct]
    recommended_skus: list[str] = Field(
        default_factory=list, description="SKUs of sources the answer actually recommends, in order"
    )
    applied_filters: ProductFilters = Field(
        description="UI/API filters merged with constraints extracted from the conversation"
    )
    model: str
