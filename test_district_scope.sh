#!/bin/bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "govtdistrict@example.com", "password": "TestPass123!"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['access'])")

echo "Got token (first 20 chars): ${TOKEN:0:20}..."
echo "---"

curl -s "http://localhost:8000/api/government/fpos/?page=1" \
  -H "Authorization: Bearer $TOKEN"
