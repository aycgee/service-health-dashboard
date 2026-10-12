"""Rastgele servislere rastgele arıza enjekte eder, bir süre sonra düzeltir.
Yaptığı her şeyi chaos_log.csv'ye yazar; böylece dashboard'daki incident'larla
karşılaştırıp monitor'ün kesintileri yakalayıp yakalamadığını doğrulayabilirsin.
Kullanım: python chaos_runner.py [döngü sayısı]
"""
import csv
import random
import sys
import time
from datetime import datetime, timezone

import httpx

CONTROL = "http://127.0.0.1:9000"
FAULTS = ["error", "slow", "flaky"]


def set_mode(client, name, mode):
    client.post(f"{CONTROL}/chaos/{name}/{mode}").raise_for_status()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{ts}  {name} -> {mode}")
    with open("chaos_log.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([ts, name, mode])


def main(rounds):
    with httpx.Client(timeout=5) as client:
        services = list(client.get(f"{CONTROL}/chaos").json())
        for _ in range(rounds):
            time.sleep(random.uniform(10, 25))          # sağlıklı dönem
            name, fault = random.choice(services), random.choice(FAULTS)
            set_mode(client, name, fault)
            time.sleep(random.uniform(20, 40))          # arıza süresi
            set_mode(client, name, "normal")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
