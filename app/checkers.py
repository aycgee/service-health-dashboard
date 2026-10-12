import time
from dataclasses import dataclass
from typing import Optional

import grpc
import httpx
from grpc_health.v1 import health_pb2, health_pb2_grpc


@dataclass
class CheckResult:
    ok: bool
    latency_ms: float
    error: Optional[str] = None


# İstemcileri her kontrolde yeniden oluşturmak yavaş (özellikle Windows'ta),
# bu yüzden bir kez oluşturup tekrar kullanıyoruz.
_http_client: Optional[httpx.AsyncClient] = None
_grpc_channels = {}


def _describe(e):
    msg = str(e).strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


async def check_http(svc, timeout):
    """REST, SOAP ve JAX-RS ağ üzerinden HTTP olduğu için aynı checker."""
    global _http_client
    if _http_client is None:
        # keep-alive kapalı: sunucu boşta kalan bağlantıyı kapatırken biz tekrar
        # kullanmaya çalışırsak yalancı 'Server disconnected' hatası alabiliyoruz.
        _http_client = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=0))
    url = f"http://{svc['host']}:{svc['port']}{svc.get('health_path', '/health')}"
    start = time.perf_counter()
    try:
        r = await _http_client.get(url, timeout=timeout)
        ms = (time.perf_counter() - start) * 1000
        if r.status_code == 200:
            return CheckResult(True, ms)
        return CheckResult(False, ms, f"HTTP {r.status_code}")
    except Exception as e:
        ms = (time.perf_counter() - start) * 1000
        return CheckResult(False, ms, _describe(e))


async def check_grpc(svc, timeout):
    """Standart grpc.health.v1.Health/Check çağrısı."""
    target = f"{svc['host']}:{svc['port']}"
    if target not in _grpc_channels:
        _grpc_channels[target] = grpc.aio.insecure_channel(target)
    stub = health_pb2_grpc.HealthStub(_grpc_channels[target])
    start = time.perf_counter()
    try:
        resp = await stub.Check(health_pb2.HealthCheckRequest(service=""), timeout=timeout)
        ms = (time.perf_counter() - start) * 1000
        if resp.status == health_pb2.HealthCheckResponse.SERVING:
            return CheckResult(True, ms)
        return CheckResult(False, ms, f"gRPC status {resp.status}")
    except Exception as e:
        ms = (time.perf_counter() - start) * 1000
        code = e.code().name if isinstance(e, grpc.aio.AioRpcError) else type(e).__name__
        return CheckResult(False, ms, f"gRPC {code}")


CHECKERS = {
    "REST": check_http,
    "SOAP": check_http,
    "JAX-RS": check_http,
    "GRPC": check_grpc,
}


async def run_check(svc, timeout):
    checker = CHECKERS[svc["protocol"].upper()]
    return await checker(svc, timeout)
