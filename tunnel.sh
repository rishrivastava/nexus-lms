#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "=========================================================="
echo " Starting Cloudflare Public Tunnel for Nexus LMS"
echo " Routing public HTTPS traffic to: http://127.0.0.1:8000"
echo "=========================================================="

exec ./bin/cloudflared tunnel --url http://127.0.0.1:8000
