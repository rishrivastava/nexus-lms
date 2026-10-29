#!/usr/bin/env bash
set -e

# Navigate to project directory
cd "$(dirname "$0")"

echo "=========================================================="
echo " Starting Nexus LMS Platform"
echo "=========================================================="
echo " Server URL: http://127.0.0.1:8000"
echo " Login Accounts (Pre-configured):"
echo "   - Student:         ID: CS2026-001  |  Pass: welcome123"
echo "   - Teacher:         ID: T-ALAN      |  Pass: teacher123"
echo "   - Department Head: ID: DEPT-HEAD   |  Pass: admin123"
echo "=========================================================="

exec ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
