import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.ai_provider import OpenAICompatibleProvider, ProviderError, configured_provider, provider_status


class AIProviderTests(unittest.TestCase):
    def test_provider_is_disabled_without_both_provider_and_key(self):
        self.assertIsNone(configured_provider(Settings()))
        self.assertIn("not configured", provider_status(Settings()))
        settings = Settings(ai_provider="openai")
        self.assertIsNone(configured_provider(settings))
        self.assertIn("missing", provider_status(settings))

    def test_openai_compatible_response_is_parsed(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"content": "  Hello from Aven.  "}}]
        }).encode()
        with patch("app.services.ai_provider.urlopen", return_value=response) as open_url:
            provider = OpenAICompatibleProvider("secret", "model", "https://api.example/v1", 8)
            self.assertEqual(provider.generate("Hi", "en"), "Hello from Aven.")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 8)

    def test_network_error_is_safe_and_not_sensitive(self):
        with patch("app.services.ai_provider.urlopen", side_effect=TimeoutError):
            provider = OpenAICompatibleProvider("secret", "model", "https://api.example/v1", 1)
            with self.assertRaisesRegex(ProviderError, "could not be reached") as error:
                provider.generate("private content", "en")
        self.assertNotIn("secret", str(error.exception))
        self.assertNotIn("private content", str(error.exception))

    def test_remote_insecure_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            OpenAICompatibleProvider("secret", "model", "http://api.example/v1", 1)


if __name__ == "__main__":
    unittest.main()