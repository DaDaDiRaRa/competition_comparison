"""Quick API diagnostic — prints the actual 400 error message from Anthropic."""
import sys, os
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))

import httpx
from config import settings

api_key = settings.api_key
print(f"API key (first 20 chars): {api_key[:20]}...")
print(f"API key length: {len(api_key)}")
print(f"Model classify: {settings.model_id_classify}")

# Minimal valid request
body = {
    "model": settings.model_id_classify,
    "max_tokens": 10,
    "temperature": 0,
    "system": "You are a test assistant.",
    "messages": [{"role": "user", "content": "Say OK"}],
}
headers = {
    "x-api-key": api_key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

print("\nSending minimal test request...")
with httpx.Client(timeout=30) as client:
    resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(f"Response body: {resp.text}")
