#!/usr/bin/env python3
"""
Verification: Server-side date range cap enforcement.
Run with: python3 test_date_range_cap.py
This sends a request that bypasses the UI to verify the server rejects it.
"""
import requests
import json
from datetime import datetime, timedelta

BACKEND_URL = 'http://localhost:8000'
# You'll need to provide a valid JWT token
JWT_TOKEN = 'YOUR_JWT_TOKEN_HERE'

def test_date_range_cap():
    # Request 500 days — should be rejected
    start = (datetime.utcnow() - timedelta(days=500)).isoformat()
    end = datetime.utcnow().isoformat()
    
    resp = requests.post(
        f'{BACKEND_URL}/api/master-view/stats',
        headers={'Authorization': f'Bearer {JWT_TOKEN}', 'Content-Type': 'application/json'},
        json={'date_start': start, 'date_end': end}
    )
    assert resp.status_code == 400, f'Expected 400, got {resp.status_code}: {resp.text}'
    print('PASS: 500-day range correctly rejected with 400')
    
    # Request 30 days — should succeed
    start = (datetime.utcnow() - timedelta(days=30)).isoformat()
    resp = requests.post(
        f'{BACKEND_URL}/api/master-view/stats',
        headers={'Authorization': f'Bearer {JWT_TOKEN}', 'Content-Type': 'application/json'},
        json={'date_start': start, 'date_end': end}
    )
    assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.text}'
    print('PASS: 30-day range correctly accepted')

if __name__ == '__main__':
    test_date_range_cap()
