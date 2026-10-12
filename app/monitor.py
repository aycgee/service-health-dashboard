import asyncio
import logging

import yaml

from .checkers import run_check
from .db import Database

log = logging.getLogger("monitor")


async def watch(svc, db, cfg):
    fails = 0
    state = "UNKNOWN"
    while True:
        r = await run_check(svc, cfg["timeout_seconds"])
        db.add_check(svc["name"], r.ok, r.latency_ms, r.error)

        if r.ok:
            fails = 0
            if state != "UP":
                db.close_incident(svc["name"])
                log.info("%s -> UP", svc["name"])
                state = "UP"
        else:
            fails += 1
            if fails >= cfg["failure_threshold"] and state != "DOWN":
                db.open_incident(svc["name"], r.error)
                log.warning("%s -> DOWN (%s)", svc["name"], r.error)
                state = "DOWN"

        await asyncio.sleep(cfg["check_interval_seconds"])


async def main(config_path="config.yaml"):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = Database(cfg["db_path"])
    for s in cfg["services"]:
        db.upsert_service(s)
    await asyncio.gather(*(watch(s, db, cfg) for s in cfg["services"]))
