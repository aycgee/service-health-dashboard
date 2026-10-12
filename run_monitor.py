import asyncio
import logging
import sys

from app.monitor import main

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

try:
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
except KeyboardInterrupt:
    pass