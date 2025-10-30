# Blue/Green Deployment with Nginx Failover

## Architecture
- **Blue Service**: Port 8081 (primary by default)
- **Green Service**: Port 8082 (backup)
- **Nginx Proxy**: Port 8080 (public endpoint)

## Configuration
All settings are controlled via `.env`:
- `BLUE_IMAGE` / `GREEN_IMAGE`: Container images
- `ACTIVE_POOL`: Which pool is primary (`blue` or `green`)
- `RELEASE_ID_BLUE` / `RELEASE_ID_GREEN`: Release identifiers

## Deployment
```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f nginx

# Stop services
docker-compose down
```


## Testing Failover
```bash
# 1. Verify Blue is active
curl -i http://localhost:8080/version

# 2. Trigger chaos on Blue
curl -X POST http://localhost:8081/chaos/start?mode=error

# 3. Verify automatic switch to Green
curl -i http://localhost:8080/version

# 4. Stop chaos
curl -X POST http://localhost:8081/chaos/stop
```

## How Failover Works
1. Nginx marks Blue as primary, Green as backup
2. When Blue returns 5xx or times out, Nginx retries the request to Green
3. After 2 failures within 5s, Nginx marks Blue as down
4. All new requests go to Green until Blue recovers
5. Client never sees errors - retry happens within the same request