import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_metrics_endpoint_returns_200_after_traffic():
    for _ in range(3):
        client.post("/echo", json={"message": "test"})
    for _ in range(2):
        client.get("/sum?a=1&b=2")
    response = client.get("/metrics", allow_redirects=True)
    assert response.status_code == 200

def test_metrics_body_contains_three_metric_families():
    response = client.get("/metrics", allow_redirects=True)
    assert "requests_total" in response.text
    assert "request_latency_seconds" in response.text
    assert "inflight_requests" in response.text

def test_echo_counter_has_expected_value():
    for _ in range(3):
        client.post("/echo", json={"message": "count_test"})
    response = client.get("/metrics", allow_redirects=True)
    
    expected_line = 'requests_total{path="/echo",status="200"}'
    found = False
    for line in response.text.splitlines():
        if expected_line in line:
            parts = line.split()
            if len(parts) >= 2:
                value = float(parts[-1])
                assert value >= 3.0
                found = True
                break
    assert found, f"Metric line {expected_line} not found or value < 3"

def test_x_request_id_header_set_on_every_non_metrics_response():
    resp_echo = client.post("/echo", json={"message": "id_test"})
    assert "x-request-id" in resp_echo.headers
    assert len(resp_echo.headers["x-request-id"]) > 0
    
    resp_sum = client.get("/sum?a=5&b=5")
    assert "x-request-id" in resp_sum.headers
    assert len(resp_sum.headers["x-request-id"]) > 0