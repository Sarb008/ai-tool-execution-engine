
from pydantic import BaseModel, ConfigDict, Field


class StrictToolArguments(BaseModel):
    """Base class for arguments accepted by registered tools."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class CheckOrderStatusArgs(StrictToolArguments):
    order_id: str = Field(
        min_length=1,
        max_length=30,
        pattern=r"^ORD-[0-9]{4,10}$",
        description="Order identifier, such as ORD-1001.",
    )


class GetBusinessHoursArgs(StrictToolArguments):
    day: str = Field(
        pattern=r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$",
        description="Full English weekday name.",
    )


class CreateSupportTicketArgs(StrictToolArguments):
    customer_id: str = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=10, max_length=2000)


class BookDemoArgs(StrictToolArguments):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    requested_day: str = Field(
        pattern=r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$"
    )
