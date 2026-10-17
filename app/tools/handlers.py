
from typing import Any

from app.database import get_connection
from app.schemas import (
    BookDemoArgs,
    CheckOrderStatusArgs,
    CreateSupportTicketArgs,
    GetBusinessHoursArgs,
)

SAMPLE_ORDERS = {
    "ORD-1001": {"status": "Processing"},
    "ORD-1002": {"status": "Shipped"},
    "ORD-1003": {"status": "Delivered"},
}

BUSINESS_HOURS = {
    "Monday": "09:00–17:00",
    "Tuesday": "09:00–17:00",
    "Wednesday": "09:00–17:00",
    "Thursday": "09:00–17:00",
    "Friday": "09:00–17:00",
    "Saturday": "10:00–14:00",
    "Sunday": "Closed",
}


def check_order_status(args: CheckOrderStatusArgs) -> dict[str, Any]:
    order = SAMPLE_ORDERS.get(args.order_id)

    if order is None:
        return {
            "found": False,
            "order_id": args.order_id,
            "message": "Order not found.",
        }

    return {
        "found": True,
        "order_id": args.order_id,
        "status": order["status"],
    }


def get_business_hours(args: GetBusinessHoursArgs) -> dict[str, str]:
    return {
        "day": args.day,
        "hours": BUSINESS_HOURS[args.day],
    }


def create_support_ticket(
    args: CreateSupportTicketArgs,
) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO support_tickets
                (customer_id, subject, description)
            VALUES (?, ?, ?)
            """,
            (args.customer_id, args.subject, args.description),
        )
        ticket_id = cursor.lastrowid

    return {
        "created": True,
        "ticket_id": ticket_id,
        "customer_id": args.customer_id,
        "subject": args.subject,
    }


def book_demo(args: BookDemoArgs) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO demo_bookings
                (name, email, requested_day)
            VALUES (?, ?, ?)
            """,
            (args.name, args.email, args.requested_day),
        )
        booking_id = cursor.lastrowid

    return {
        "created": True,
        "booking_id": booking_id,
        "name": args.name,
        "requested_day": args.requested_day,
    }
