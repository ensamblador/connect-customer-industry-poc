"""
Airline flights Lambda handler.

Backs the /flights endpoints of the airline self-service REST API:

    GET /flights?origin=BOG&destination=MDE  -> list flights, optionally filtered
    GET /flights/{flightId}                  -> a single flight's details

Reads from the DynamoDB flights table (env FLIGHTS_TABLE). The catalog is
small, so listing uses Scan and filters origin/destination in the handler.
"""

import json
import os
from decimal import Decimal

import boto3

_TABLE_NAME = os.environ["FLIGHTS_TABLE"]
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def _flight_label(flight: dict) -> str:
    """Spanish, human-readable label for a flight,
    e.g. 'AL100 Bogotá → Medellín — 2026-08-15 06:30 — $89 USD'."""
    route = (
        f"{flight['flightId'].replace('flight-', '')} "
        f"{flight.get('originCity', flight.get('origin', ''))} → "
        f"{flight.get('destinationCity', flight.get('destination', ''))}"
    )
    parts = [route]
    if flight.get("departureDate"):
        parts.append(f"{flight['departureDate']} {flight.get('departureTime', '')}")
    if flight.get("price") is not None:
        parts.append(f"${flight['price']} {flight.get('currency', 'USD')}")
    return " — ".join(parts)


def _handle_connect_event(_event) -> dict:
    """Amazon Connect 'Invoke AWS Lambda function' entry point (ResponseType: JSON).

    Returns nested JSON the contact flow reads under ``$.External``.
    ``flightOptions`` is pre-shaped as the view Dropdown's ``Option[]``
    (``{Label, Value}``) — ``Label`` is a Spanish, human-readable string and
    ``Value`` is the ``flightId`` — because the flow cannot map arrays itself.
    """
    raw_flights = _table.scan().get("Items", [])
    # Sort by departure date+time for a predictable, helpful order.
    raw_flights.sort(
        key=lambda f: (f.get("departureDate", ""), f.get("departureTime", ""))
    )

    # Normalize DynamoDB Decimals to native JSON numbers.
    flights = json.loads(json.dumps(raw_flights, default=_json_default))

    flight_options = [
        {"Label": _flight_label(flight), "Value": flight["flightId"]}
        for flight in flights
    ]

    return {
        "flights": flights,
        "flightOptions": flight_options,
        "count": len(flights),
    }


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    # Amazon Connect "Invoke AWS Lambda function" events carry a top-level
    # "Details" key and no "httpMethod"; serve them the view-ready JSON payload.
    if isinstance(event, dict) and "Details" in event and "httpMethod" not in event:
        return _handle_connect_event(event)

    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    flight_id = path_params.get("flightId")

    # GET /flights/{flightId}
    if flight_id:
        result = _table.get_item(Key={"flightId": flight_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"flight {flight_id} not found"})
        return _response(200, item)

    # GET /flights?origin=...&destination=...
    flights = _table.scan().get("Items", [])

    origin = query_params.get("origin")
    if origin:
        flights = [f for f in flights if f.get("origin", "").upper() == origin.upper()]

    destination = query_params.get("destination")
    if destination:
        flights = [
            f for f in flights if f.get("destination", "").upper() == destination.upper()
        ]

    # Sort by departure date+time ascending.
    flights.sort(
        key=lambda f: (f.get("departureDate", ""), f.get("departureTime", ""))
    )
    return _response(200, {"flights": flights, "count": len(flights)})
