import os
import time
import subprocess
import requests
from collections import deque
from datetime import datetime

LOG_FILE = "/var/log/nginx/access.log"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ACTIVE_POOL = os.environ.get("ACTIVE_POOL", "blue")
ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", 2))
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", 200))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", 300))
REQUIRED_FIELDS = ["pool", "upstream_status", "request"]

last_alert_time = 0
last_pool = ACTIVE_POOL
last_error_state = False  # Track if we were in error state
status_window = deque(maxlen=WINDOW_SIZE)
missing_fields_count = 0
total_logs_count = 0

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
        
        total_logs_count += 1
        pool = "unknown"
        status = 0
        found_fields = []
        headers_valid = True
        
        try:
            # Parse log fields
            for part in line.split():
                if part.startswith("pool="):
                    pool = part.split("=")[1]
                    found_fields.append("pool")
                if part.startswith("upstream_status="):
                    status_str = part.split("=")[1].split(",")[0]
                    status = int(status_str)
                    found_fields.append("upstream_status")
                if part.startswith("request=") or '"GET ' in part or '"POST ' in part:
                    found_fields.append("request")
            
            # Check for missing required fields
            missing = [f for f in REQUIRED_FIELDS if f not in found_fields]
            if missing:
                missing_fields_count += 1
                missing_ratio = (missing_fields_count / total_logs_count) * 3
                print(f"Missing fields: {missing} ({missing_ratio:.1f}/3)", flush=True)
                
                if missing_ratio >= 1 and total_logs_count % 50 == 0:  # Alert periodically
                    send_slack_alert(
                        "Nginx Logs Missing Fields",
                        f"Detected incomplete log entries",
                        {
                            "Missing Count": f"{missing_fields_count}",
                            "Total Logs": f"{total_logs_count}",
                            "Ratio": f"{missing_ratio:.1f}/3",
                            "Recent Missing": ", ".join(missing),
                            "Timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                    )
            
            # Check for HTTP 000 (endpoint failed)
            if status == 0 or status == 000:
                send_slack_alert(
                    "Endpoint Failed (HTTP 000)",
                    f"Upstream returned status 000 - endpoint unreachable",
                    {
                        "Pool": pool,
                        "Status": "000",
                        "Timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                )
                continue
            
            # Check for invalid headers (5xx with missing expected headers)
            if 500 <= status < 600 and "upstream_status" not in found_fields:
                headers_valid = False
                send_slack_alert(
                    "Headers Incorrect",
                    f"Error response missing expected upstream headers",
                    {
                        "Status": status,
                        "Pool": pool,
                        "Timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                )
                
        except Exception as e:
            print(f"Parse error: {e}", flush=True)
            continue
        
        if status == 0:
            continue
        
        status_window.append(status)
        errors = sum(1 for s in status_window if 500 <= s < 600)
        error_rate = (errors / len(status_window)) * 100 if status_window else 0
        
        print(f"Status: {status}, Error rate: {error_rate:.2f}%, Pool: {pool}", flush=True)
        
        # Check for failover from blue to green
        if pool != "unknown" and pool != "-" and pool != last_pool:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                if last_pool == ACTIVE_POOL and pool != ACTIVE_POOL:
                    send_slack_alert(
                        "Failover to Green Detected",
                        f"System failed over from {last_pool} → {pool}",
                        {
                            "From Pool": last_pool,
                            "To Pool": pool,
                            "Error Rate": f"{error_rate:.2f}%",
                            "Timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                    )
                # Check for recovery back to blue
                elif last_pool != ACTIVE_POOL and pool == ACTIVE_POOL:
                    send_slack_alert(
                        "Recovery to Blue Detected",
                        f"System recovered from {last_pool} → {pool}",
                        {
                            "From Pool": last_pool,
                            "To Pool": pool,
                            "Error Rate": f"{error_rate:.2f}%",
                            "Timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                    )
                else:
                    send_slack_alert(
                        "Pool Switch Detected",
                        f"Pool changed from {last_pool} → {pool}",
                        {"Timestamp": datetime.utcnow().isoformat() + "Z"}
                    )
                last_alert_time = now
            last_pool = pool
        
        # Check for high error rate
        if error_rate > ERROR_RATE_THRESHOLD:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC and not last_error_state:
                send_slack_alert(
                    "Error Rate Alert",
                    f"Error rate exceeded threshold: {error_rate:.2f}%",
                    {
                        "Error Rate": f"{error_rate:.2f}%",
                        "Threshold": f"{ERROR_RATE_THRESHOLD}%",
                        "Window": f"{WINDOW_SIZE}",
                        "Pool": pool,
                        "Timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                )
                last_alert_time = now
                last_error_state = True
        # Check for recovery from high error rate
        elif error_rate <= ERROR_RATE_THRESHOLD and last_error_state:
            now = time.time()
            if now - last_alert_time > ALERT_COOLDOWN_SEC:
                send_slack_alert(
                    "Error Rate Recovery",
                    f"Error rate returned to normal: {error_rate:.2f}%",
                    {
                        "Error Rate": f"{error_rate:.2f}%",
                        "Threshold": f"{ERROR_RATE_THRESHOLD}%",
                        "Pool": pool,
                        "Timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                )
                last_alert_time = now
                last_error_state = False
                
except KeyboardInterrupt:
    process.terminate()
