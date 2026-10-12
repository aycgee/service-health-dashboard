"""Çalıştır:  python -m pytest -v
(önce:  pip install pytest)
"""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import monitor
from app.checkers import CheckResult, check_http
from app.db import Database

OK = CheckResult(True, 5.0)
FAIL = CheckResult(False, 5.0, "HTTP 500")
SVC = {"name": "TestService", "protocol": "REST", "host": "127.0.0.1", "port": 1}
CFG = {"timeout_seconds": 1, "check_interval_seconds": 0, "failure_threshold": 3}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def run_watch(db, results, monkeypatch):
    """watch() döngüsünü, verilen sonuç dizisi bitene kadar çalıştırır."""
    it = iter(results)

    async def fake_run_check(svc, timeout):
        try:
            return next(it)
        except StopIteration:
            raise asyncio.CancelledError

    monkeypatch.setattr(monitor, "run_check", fake_run_check)
    try:
        asyncio.run(monitor.watch(SVC, db, CFG))
    except asyncio.CancelledError:
        pass


def incidents(db):
    return db.conn.execute("SELECT * FROM incidents").fetchall()


# ---- monitor mantığı ----

def test_tek_veya_iki_hata_incident_acmaz(db, monkeypatch):
    run_watch(db, [OK, FAIL, FAIL, OK], monkeypatch)
    assert incidents(db) == []


def test_ust_uste_uc_hata_incident_acar(db, monkeypatch):
    run_watch(db, [OK, FAIL, FAIL, FAIL], monkeypatch)
    rows = incidents(db)
    assert len(rows) == 1
    assert rows[0]["ended_at"] is None
    assert rows[0]["reason"] == "HTTP 500"


def test_servis_duzelince_incident_kapanir(db, monkeypatch):
    run_watch(db, [OK, FAIL, FAIL, FAIL, OK], monkeypatch)
    rows = incidents(db)
    assert len(rows) == 1
    assert rows[0]["ended_at"] is not None


def test_arada_basari_hata_sayacini_sifirlar(db, monkeypatch):
    run_watch(db, [OK, FAIL, FAIL, OK, FAIL, FAIL, OK], monkeypatch)
    assert incidents(db) == []


def test_uzun_kesintide_tek_incident_olur(db, monkeypatch):
    run_watch(db, [OK] + [FAIL] * 10, monkeypatch)
    assert len(incidents(db)) == 1


def test_her_kontrol_kaydedilir(db, monkeypatch):
    run_watch(db, [OK, FAIL, OK], monkeypatch)
    n = db.conn.execute("SELECT COUNT(*) FROM health_checks").fetchone()[0]
    assert n == 3


# ---- veritabanı ----

def test_acik_incident_tekrar_acilmaz(db):
    db.open_incident("A", "x")
    db.open_incident("A", "x")
    assert len(incidents(db)) == 1


def test_incident_kapatma_sadece_ilgili_servisi_etkiler(db):
    db.open_incident("A", "x")
    db.open_incident("B", "y")
    db.close_incident("A")
    assert db.get_open_incident("A") is None
    assert db.get_open_incident("B") is not None


# ---- HTTP checker (gerçek küçük bir sunucuyla) ----

def start_server(status):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"x")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def svc_for(server):
    return {"name": "T", "protocol": "REST", "host": "127.0.0.1",
            "port": server.server_address[1], "health_path": "/health"}


def test_http_200_saglikli():
    server = start_server(200)
    r = asyncio.run(check_http(svc_for(server), 2))
    server.shutdown()
    assert r.ok and r.error is None


def test_http_500_basarisiz():
    server = start_server(500)
    r = asyncio.run(check_http(svc_for(server), 2))
    server.shutdown()
    assert not r.ok and r.error == "HTTP 500"


def test_servis_kapaliysa_basarisiz():
    server = start_server(200)
    svc = svc_for(server)
    server.shutdown()
    server.server_close()
    r = asyncio.run(check_http(svc, 1))
    assert not r.ok and r.error
