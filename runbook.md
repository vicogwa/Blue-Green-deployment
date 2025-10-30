# Blue-Green Deployment Runbook

## Alert Types and Response Procedures

### 1. Failover Detected Alert

**Alert Message:** "Failover Detected - Pool switched from [source] → [destination]"

**What it means:**
- The primary application pool has failed or become unhealthy
- Nginx has automatically switched traffic to the backup pool
- This indicates potential issues with the failed pool

**Immediate Actions:**
1. Check the status of the failed pool container:
```bash
   sudo docker ps -a | grep app_
```

2. Review logs of the failed container:
```bash
   sudo docker logs app_blue  # or app_green
```

3. Check health status:
```bash
   sudo docker inspect app_blue | grep -A 10 Health
```

4. If the container is down, attempt restart:
```bash
   sudo docker start app_blue
```

5. Monitor for successful recovery:
```bash
   sudo docker logs -f alert_watcher
```

**Root Cause Investigation:**
- Review application logs for errors
- Check resource usage (CPU, memory)
- Verify network connectivity between containers
- Check if deployment introduced bugs

---

### 2. Error Rate Detected Alert

**Alert Message:** "Error Rate Detected - Error rate: X.XX% (threshold: 2.0%)"

**What it means:**
- The application is returning 5xx errors at a rate exceeding the configured threshold (2%)
- Measured over a rolling window of 200 requests
- Could indicate application bugs, resource exhaustion, or infrastructure issues

**Immediate Actions:**
1. Check current error rate in nginx logs:
```bash
   sudo docker exec nginx_proxy cat /var/log/nginx/access.log | tail -50 | grep -E "50[0-9]"
```

2. Identify which pool is affected:
```bash
   sudo docker logs alert_watcher | tail -20
```

3. Check application container health:
```bash
   sudo docker ps
   sudo docker logs app_blue --tail 50
   sudo docker logs app_green --tail 50
```

4. Review resource usage:
```bash
   sudo docker stats --no-stream
```

5. If errors persist, consider rolling back:
   - Update `.env` to switch `ACTIVE_POOL` to the stable version
   - Restart nginx: `sudo docker compose restart nginx`

**Root Cause Investigation:**
- Analyze error patterns in logs
- Check for recent deployments or configuration changes
- Verify database/external service connectivity
- Review application metrics and resource utilization

---

## Configuration Details

### Alert Thresholds
- **Error Rate Threshold:** 2.0% (configurable via `ERROR_RATE_THRESHOLD`)
- **Window Size:** 200 requests (configurable via `WINDOW_SIZE`)
- **Alert Cooldown:** 300 seconds (5 minutes) between alerts

### Architecture
- **Blue Pool:** app_blue container on port 8081
- **Green Pool:** app_green container on port 8082
- **Public Access:** Nginx proxy on port 8080
- **Failover:** Automatic via Nginx upstream backup configuration

### Health Checks
- Endpoint: `/healthz`
- Interval: 5 seconds
- Timeout: 3 seconds
- Retries: 2

---

## Monitoring Commands

### View Real-time Alerts
```bash
sudo docker logs -f alert_watcher
```

### Check Container Status
```bash
sudo docker ps -a
```

### View Nginx Logs
```bash
sudo docker exec nginx_proxy cat /var/log/nginx/access.log | tail -50
```

### Check Active Pool
```bash
grep ACTIVE_POOL .env
```

### Manual Failover
1. Edit `.env` and change `ACTIVE_POOL=blue` to `ACTIVE_POOL=green` (or vice versa)
2. Restart nginx: `sudo docker compose restart nginx`

---

## Escalation Path

**Severity Levels:**

- **P1 (Critical):** Both pools failing, no traffic being served
  - Immediate escalation to on-call engineer
  - Check infrastructure (Docker daemon, host resources)

- **P2 (High):** Single pool failing with active errors >10%
  - Investigate within 15 minutes
  - Consider rollback if issue not resolved quickly

- **P3 (Medium):** Error rate 2-5%, service degraded but functional
  - Investigate within 1 hour
  - Monitor for escalation

- **P4 (Low):** Single failover event with recovery
  - Document in incident log
  - Investigate during business hours

---

## Contact Information

- **Slack Channel:** #blue-green-alerts
- **On-Call Rotation:** [Your team's rotation schedule]
- **Documentation:** [Link to your docs]

---

## Revision History

- 2025-10-30: Initial runbook creation
