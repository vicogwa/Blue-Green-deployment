import os
import time
import subprocess
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
    payload = {"text": f"*{title}*\n{text}"}
    if extra:
        for k, v in extra.items():
            payload["text"] += f"\n{k}: {v}"
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
        print(f"Slack alert sent: {title}", flush=True)
    except Exception as e:
        print(f"Failed to send Slack alert: {e}", flush=True)

print(f"Starting alert watcher...", flush=True)
print(f"LOG_FILE: {LOG_FILE}", flush=True)
print(f"ACTIVE_POOL: {ACTIVE_POOL}", flush=True)
print(f"ERROR_RATE_THRESHOLD: {ERROR_RATE_THRESHOLD}%", flush=True)
print(f"WINDOW_SIZE: {WINDOW_SIZE}", flush=True)

while not os.path.exists(LOG_FILE):
    print(f"Waiting for log file...", flush=True)
    time.sleep(2)

print(f"Log file found. Monitoring...", flush=True)

# Use tail with line buffering
process = subprocess.Popen(
    ['tail', '-F', '-n', '0', LOG_FILE],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    bufsize=1,
    universal_newlines=True
)

try:
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue
        
        print(f"Processing: {line[:100]}...", flush=True)
            
        pool = "unknown"
        status = 0
        try:
            for part in line.split():
                if part.startswith("pool="):
                    pool = part.split("=")[1]
                if part.startswith("upstream_status="):
                    # Handle multiple statuses like "504, 504"
                    status_str = part.split("=")[1].split(",")[0]
                    status = int(status_str)
        except Exception as e:
            print(f"Parse error: {e}", flush=True)
            continue

        if status == 0:
            continue

        status_window.append(status)
        errors = sum(1 for s in status_window if 500 <= s < 600)
        error_rate = (errors / len(status_window)) * 100 if status_window else 0

        print(f"Status: {status}, Error rate: {error_rate:.2f}%, Pool: {pool}", flush=True)

        if pool != "unknown" and pool != "-" and pool != last_pool:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                send_slack_alert("Failover Detected", f"Pool switched from {last_pool} → {pool}", {"Timestamp": datetime.utcnow().isoformat() + "Z"})
                last_alert_time = now
            last_pool = pool

        if error_rate > ERROR_RATE_THRESHOLD:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                send_slack_alert("Error Rate Detected", f"Error rate: {error_rate:.2f}%", {
                    "Error Rate": f"{error_rate:.2f}%",
                    "Threshold": f"{ERROR_RATE_THRESHOLD}%",
                    "Window": f"{WINDOW_SIZE}",
                    "Pool": pool,
                    "Timestamp": datetime.utcnow().isoformat() + "Z"
                })
                last_alert_time = now
except KeyboardInterrupt:
    process.terminate()
