#!/bin/bash
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
cd /Users/wenmingdeapple/Claude/P001-jd-pcs
python3 scripts/daily_job.py >> logs/cron-$(date +%Y%m%d).log 2>&1
