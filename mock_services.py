"""config.yaml'daki tüm servisleri sahte olarak ayağa kaldırır.
Her servisin davranışı bir 'chaos modu' ile değiştirilebilir:
  normal -> sağlıklı
  error  -> HTTP 500 / gRPC NOT_SERVING
  slow   -> timeout'u aşacak kadar geç yanıt verir
  flaky  -> istekların ~%50'si hata verir
Kontrol API'si: http://127.0.0.1:9000
  GET  /chaos                -> tüm servislerin modu
  POST /chaos/{servis}/{mod} -> modu değiştir
"""
import asyncio
import contextlib
import random
import sys

import grpc
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Response
from grpc_health.v1 import health_pb2, health_pb2_grpc

CONTROL_PORT = 9000
MODES = {"normal", "error", "slow", "flaky"}
state = {}  # servis adı -> mod


def should_fail(name):
    mode = state[name]
    return mode == "error" or (mode == "flaky" and random.random() < 0.5)


def make_http_app(name, protocol, health_path):
    app = FastAPI()

    @app.get(health_path)
    async def health():
        if state[name] == "slow":
            await asyncio.sleep(10)
        if should_fail(name):
            return Response(status_code=500, content="simulated failure")
        if protocol.upper() == "SOAP":
            xml = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                   '<soap:Body><status>UP</status></soap:Body></soap:Envelope>')
            return Response(content=xml, media_type="text/xml")
        return {"status": "UP"}

    return app


class ChaosHealth(health_pb2_grpc.HealthServicer):
    def __init__(self, name):
        self.name = name

    async def Check(self, request, context):
        if state[self.name] == "slow":
            await asyncio.sleep(10)
        status = (health_pb2.HealthCheckResponse.NOT_SERVING if should_fail(self.name)
                  else health_pb2.HealthCheckResponse.SERVING)
        return health_pb2.HealthCheckResponse(status=status)


async def serve_grpc(name, host, port):
    server = grpc.aio.server()
    health_pb2_grpc.add_HealthServicer_to_server(ChaosHealth(name), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    await server.wait_for_termination()


class QuietServer(uvicorn.Server):
    """Birden fazla uvicorn tek süreçte: sinyal yönetimini biz yapıyoruz."""
    @contextlib.contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self):
        pass


async def serve_http(app, host, port):
    cfg = uvicorn.Config(app, host=host, port=port, log_level="warning")
    await QuietServer(cfg).serve()


def make_control_app():
    app = FastAPI()

    @app.get("/chaos")
    def get_state():
        return state

    @app.post("/chaos/{name}/{mode}")
    def set_mode(name: str, mode: str):
        if name not in state:
            raise HTTPException(404, f"unknown service {name}")
        if mode not in MODES:
            raise HTTPException(400, f"mode must be one of {sorted(MODES)}")
        state[name] = mode
        return {name: mode}

    return app


async def main(config_path):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    tasks = []
    for s in cfg["services"]:
        state[s["name"]] = "normal"
        if s["protocol"].upper() == "GRPC":
            tasks.append(serve_grpc(s["name"], s["host"], s["port"]))
        else:
            app = make_http_app(s["name"], s["protocol"], s.get("health_path", "/health"))
            tasks.append(serve_http(app, s["host"], s["port"]))
        print(f"mock: {s['name']} ({s['protocol']}) -> {s['host']}:{s['port']}")

    tasks.append(serve_http(make_control_app(), "127.0.0.1", CONTROL_PORT))
    print(f"chaos kontrol API: http://127.0.0.1:{CONTROL_PORT}/chaos")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
    except KeyboardInterrupt:
        pass
