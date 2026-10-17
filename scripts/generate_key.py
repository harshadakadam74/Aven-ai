"""Print a random API key for AVEN_AI_API_KEY. Run: python scripts/generate_key.py"""

import secrets

print(secrets.token_urlsafe(32))
