import contextvars
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware

requests_total = Counter(
    "requests_total",
    "Total HTTP requests",
    ["path", "status"]
)

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "Request latency in seconds",
    ["path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

inflight_requests = Gauge(
    "inflight_requests",
    "In-flight requests"
)

request_id_var = contextvars.ContextVar("request_id", default="")

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = uuid.uuid4().hex
        request_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        latency_ms = round(duration * 1000, 2)
        
        log_payload = {
            "ts": time.time(),
            "level": "INFO",
            "request_id": request_id_var.get(),
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms
        }
        logger.info(json.dumps(log_payload))
        return response

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        is_metrics = request.url.path in ["/metrics", "/metrics/"]
        
        if not is_metrics:
            inflight_requests.inc()
            
        start_time = time.time()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.time() - start_time
            if not is_metrics:
                inflight_requests.dec()
                if response is not None:
                    requests_total.labels(path=request.url.path, status=str(response.status_code)).inc()
                    request_latency_seconds.labels(path=request.url.path).observe(duration)

class EchoRequest(BaseModel):
    message: str

app = FastAPI(title="M11 Drill — Toy FastAPI Service")

app.add_middleware(MetricsMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

@app.post("/echo")
def echo(req: EchoRequest):
    return {"echo": req.message}

@app.get("/sum")
def sum_endpoint(a: int = 0, b: int = 0):
    return {"sum": a + b}

app.mount("/metrics", make_asgi_app())