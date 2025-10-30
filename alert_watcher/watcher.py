import os
import time
import requests
from collections import deque
from datetime import datetime

LOG_FILE = "/var/log/nginx/access.log"

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ACTIVE_POOL = os.environ.get("ACTIVE_POOL")
ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", 2))
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", 200))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", 300))

last_alert_time = 0
last_pool = ACTIVE_POOL
status_window = deque(maxlen=WINDOW_SIZE)

def send_slack_alert(title, text, extra=None):
    payload = {
        "text": f"*{title}*\n{text}"
    }
    if extra:
        for k, v in extra.items():
            payload["text"] += f"\n{k}: {v}"
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
        print(f"Slack alert sent: {title}")
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")

def follow(file):
    file.seek(0, os.SEEK_END)
    while True:
        line = file.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

print(f"Starting alert watcher...")
print(f"LOG_FILE: {LOG_FILE}")
print(f"ACTIVE_POOL: {ACTIVE_POOL}")
print(f"ERROR_RATE_THRESHOLD: {ERROR_RATE_THRESHOLD}%")
print(f"WINDOW_SIZE: {WINDOW_SIZE}")

with open(LOG_FILE, "r") as f:
    log_lines = follow(f)
    for line in log_lines:
        # parse fields
        pool = "unknown"
        status = 0
        parts = line.split()
        try:
            for part in parts:
                if part.startswith("pool="):
                    pool = part.split("=")[1]
                if part.startswith("upstream_status="):
                    status = int(part.split("=")[1])
        except Exception:
            continue

        # track rolling error rate
        status_window.append(status)
        errors = sum(1 for s in status_window if 500 <= s < 600)
        error_rate = (errors / len(status_window)) * 100 if status_window else 0

        # failover detection
        if pool != last_pool:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                send_slack_alert(
                    "Failover Detected",
                    f"Pool switched from {last_pool} → {pool}",
                    {"Timestamp": datetime.utcnow().isoformat() + "Z"}
                )
                last_alert_time = now
            last_pool = pool

        # error rate alert
        if error_rate > ERROR_RATE_THRESHOLD:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                send_slack_alert(
                    "Error Rate Detected",
                    f"Error rate has exceeded threshold: {error_rate:.2f}% (threshold: {ERROR_RATE_THRESHOLD}%)",
                    {
                        "Error Rate": f"{error_rate:.2f}%",
                        "Threshold": f"{ERROR_RATE_THRESHOLD}%",
                        "Window Size": f"{WINDOW_SIZE} requests",
                        "Current Pool": pool,
                        "Timestamp": datetime.utcnow().isoformat() + "Z",
                        "Action": "See runbook.md for response procedures"
                    }
                )
                last_alert_time = now
