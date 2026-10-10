import json
import random
import uuid

from app.messages import dump, task_payload
from worker.sim import handle_task, outcome_for, parse_args


class Sink:
    def __init__(self):
        self.bodies = []

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.bodies.append(json.loads(body))


def _task_body():
    return dump(task_payload(uuid.uuid4(), "deploy", uuid.uuid4()))


def test_fail_rate_zero_finishes_done(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.4)
    sink = Sink()
    result = handle_task(sink, "q", _task_body(), 0, 0, 0, sleep=lambda _s: None)
    assert result == "ack"
    assert [item["status"] for item in sink.bodies] == ["in_progress", "done"]
    assert sink.bodies[0]["update_id"] != sink.bodies[1]["update_id"]


def test_fail_rate_one_finishes_failed(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    sink = Sink()
    result = handle_task(sink, "q", _task_body(), 1, 0, 0, sleep=lambda _s: None)
    assert result == "ack"
    assert [item["status"] for item in sink.bodies] == ["in_progress", "failed"]


def test_bad_task_is_dropped():
    sink = Sink()
    assert handle_task(sink, "q", b"{}", 0, 0, 0, sleep=lambda _s: None) == "dlq"
    assert sink.bodies == []


def test_outcome_bounds():
    assert outcome_for(0) == "done"
    assert outcome_for(1) == "failed"


def test_parse_args_from_cli():
    args = parse_args(["--fail-rate", "1", "--min-delay-ms", "10", "--max-delay-ms", "20"])
    assert args.fail_rate == 1
    assert args.min_delay_ms == 10
    assert args.max_delay_ms == 20
