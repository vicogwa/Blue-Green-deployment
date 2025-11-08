#!/bin/sh
set -e

LOG_DIR=/var/log/nginx
mkdir -p $LOG_DIR

# Remove default symlinks and create real log files
rm -f /var/log/nginx/access.log /var/log/nginx/error.log
touch /var/log/nginx/access.log /var/log/nginx/error.log

echo "[entrypoint] Generating nginx config for ACTIVE_POOL=${ACTIVE_POOL}"

if [ "${ACTIVE_POOL}" = "blue" ]; then
    PRIMARY="app_blue:${APP_PORT}"
    BACKUP="app_green:${APP_PORT}"
else
    PRIMARY="app_green:${APP_PORT}"
    BACKUP="app_blue:${APP_PORT}"
fi

echo "[entrypoint] Generated nginx config:"
echo "  Primary: ${PRIMARY}"
echo "  Backup: ${BACKUP}"

# Nginx config with extended log format for operational visibility
cat > /etc/nginx/conf.d/default.conf <<'EOF'
log_format custom '$remote_addr - $remote_user [$time_local] '
                  '"$request" $status $body_bytes_sent '
                  'pool=$upstream_addr '
                  'release=$upstream_http_x_release_id '
                  'upstream_status=$upstream_status '
                  'request_time=$request_time '
                  'upstream_response_time=$upstream_response_time';

upstream backend {
    server PRIMARY_PLACEHOLDER max_fails=2 fail_timeout=5s;
    server BACKUP_PLACEHOLDER backup;
}

server {
    listen 80;
    server_name localhost;
    
    access_log /var/log/nginx/access.log custom;
    error_log /var/log/nginx/error.log info;
    
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        
        proxy_connect_timeout 2s;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;
        
        proxy_next_upstream error timeout http_500 http_502 http_503 http_504;
        proxy_next_upstream_tries 2;
        proxy_next_upstream_timeout 10s;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_pass_header X-App-Pool;
        proxy_pass_header X-Release-Id;
        
        proxy_buffering off;
    }
}
EOF

# Replace placeholders
sed -i "s|PRIMARY_PLACEHOLDER|${PRIMARY}|g" /etc/nginx/conf.d/default.conf
sed -i "s|BACKUP_PLACEHOLDER|${BACKUP}|g" /etc/nginx/conf.d/default.conf

# Test nginx config
nginx -t

echo "[entrypoint] Config test passed. Starting nginx..."
exec nginx -g "daemon off;"
