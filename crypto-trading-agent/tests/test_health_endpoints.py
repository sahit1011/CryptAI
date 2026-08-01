"""Health endpoints must tell the truth about dependencies.

Regression cover for a live production bug found 2026-08-02: `/health` reported
`"message_bus": message_bus is not None`. `startup_event` catches a Redis connection
failure and carries on, so the object exists either way and the endpoint reported a
broken instance as fully healthy — while `render.yaml` was probing exactly that path.

The three endpoints have deliberately different contracts:
  /health        report for humans/dashboards. Always 200; body says online|degraded.
  /health/live   liveness. Never checks dependencies — a dead Redis must not make the
                 orchestrator restart the pod.
  /health/ready  readiness. 503 when deps are down so load balancers steer away.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import src.api.server as server


@pytest.fixture
def client():
    # Plain construction (not a context manager) so the lifespan/startup hook never
    # runs — these tests must not try to reach a real Redis.
    return TestClient(server.app)


def _bus(ping_result=True, ping_error=None):
    bus = MagicMock()
    bus.redis_client.ping = AsyncMock(
        side_effect=ping_error, return_value=ping_result
    )
    return bus


def test_health_reports_online_when_redis_answers(client, monkeypatch):
    monkeypatch.setattr(server, "message_bus", _bus(ping_result=True))
    body = client.get("/health").json()
    assert body["status"] == "online"
    assert body["message_bus"] is True


def test_health_is_not_fooled_by_a_constructed_but_dead_bus(client, monkeypatch):
    """THE regression. A MessageBus object exists but Redis is unreachable.

    `message_bus is not None` is True here. Reporting healthy on that basis is what
    let a broken production instance keep taking traffic.
    """
    monkeypatch.setattr(
        server, "message_bus", _bus(ping_error=ConnectionError("Error 61 connecting"))
    )
    body = client.get("/health").json()
    assert body["message_bus"] is False, "dead Redis reported as a healthy message bus"
    assert body["status"] == "degraded"


def test_health_handles_no_bus_at_all(client, monkeypatch):
    monkeypatch.setattr(server, "message_bus", None)
    body = client.get("/health").json()
    assert body["message_bus"] is False
    assert body["status"] == "degraded"


def test_health_stays_200_even_when_degraded(client, monkeypatch):
    """It is a report, not a gate. Flipping it to 5xx would make it a restart trigger."""
    monkeypatch.setattr(server, "message_bus", _bus(ping_error=ConnectionError("down")))
    assert client.get("/health").status_code == 200


def test_health_live_ignores_dependencies(client, monkeypatch):
    """Liveness must stay green with every dependency dead, or Render restart-loops."""
    monkeypatch.setattr(server, "message_bus", None)
    monkeypatch.setattr(server, "trade_history_manager", None, raising=False)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_health_ready_503s_when_dependencies_are_down(client, monkeypatch):
    monkeypatch.setattr(server, "message_bus", None)
    monkeypatch.setattr(server, "trade_history_manager", None, raising=False)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"] is False


def test_render_probes_liveness_not_the_reporting_endpoint():
    """render.yaml must point at /health/live.

    /health/ready would restart-loop the pod whenever Redis blips; /health is a human
    report that always 200s and so would never fail a probe at all.
    """
    import pathlib

    import yaml

    render = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parents[1] / "render.yaml").read_text()
    )
    web = [s for s in render["services"] if s.get("type") == "web"]
    assert web, "no web service in render.yaml"
    for svc in web:
        assert svc.get("healthCheckPath") == "/health/live", (
            f"{svc['name']} probes {svc.get('healthCheckPath')} — must be /health/live"
        )
