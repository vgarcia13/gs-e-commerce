import json
import logging

import pytest
from django.urls import reverse

from config.logging import (
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    clean_request_id,
    request_id_var,
)
from config.middleware import REQUEST_ID_HEADER


def make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="ordering.services",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="Order %s placed",
        args=("ORD-2026-00001",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_parseable_json_with_extras():
    record = make_record(event="order.placed", actor_id=7, amount="99.99")

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "ordering.services"
    assert payload["message"] == "Order ORD-2026-00001 placed"
    assert payload["event"] == "order.placed"
    assert payload["actor_id"] == 7
    assert payload["amount"] == "99.99"
    assert "timestamp" in payload


def test_json_formatter_serialises_unexpected_types():
    record = make_record(event="order.placed", product=object())

    payload = json.loads(JsonFormatter().format(record))

    assert isinstance(payload["product"], str)


def test_json_formatter_includes_the_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = make_record(event="import.row_failed")
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_text_formatter_appends_extras():
    formatter = TextFormatter(fmt="{levelname} {message}", style="{")
    record = make_record(event="order.placed", actor_id=7, request_id="abc")

    line = formatter.format(record)

    assert "event=order.placed" in line
    assert "actor_id=7" in line


def test_request_id_filter_injects_the_current_value():
    token = request_id_var.set("req-123")
    record = make_record()
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)

    assert record.request_id == "req-123"


@pytest.mark.parametrize(
    "supplied",
    ["", None, "has spaces", "a" * 65, "semi;colon", "new\nline"],
)
def test_unsafe_request_ids_are_replaced(supplied):
    assert clean_request_id(supplied) != supplied


def test_safe_request_id_is_reused():
    assert clean_request_id("abc-123_XYZ.4") == "abc-123_XYZ.4"


@pytest.mark.django_db
def test_response_carries_a_request_id(client):
    response = client.get(reverse("catalog:product_list"))

    assert response[REQUEST_ID_HEADER]


@pytest.mark.django_db
def test_supplied_request_id_is_echoed_back(client):
    response = client.get(
        reverse("catalog:product_list"), headers={"x-request-id": "trace-abc-1"}
    )

    assert response[REQUEST_ID_HEADER] == "trace-abc-1"


@pytest.mark.django_db
def test_forged_request_id_is_not_echoed_back(client):
    response = client.get(
        reverse("catalog:product_list"), headers={"x-request-id": "bad value\nINJECTED"}
    )

    assert response[REQUEST_ID_HEADER] != "bad value\nINJECTED"
