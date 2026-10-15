"""User-facing Gemini / A2A error mapping."""

import unittest

from agents.llm_errors import user_facing_llm_error


class LlmErrorsTest(unittest.TestCase):
    def test_quota(self) -> None:
        err = RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
        self.assertIn("quota", user_facing_llm_error(err).lower())

    def test_api_key(self) -> None:
        err = RuntimeError("API key not valid. Please pass a valid API key.")
        self.assertIn("api key", user_facing_llm_error(err).lower())

    def test_jsonrpc_internal(self) -> None:
        err = RuntimeError(
            "JSON-RPC Error code=-32603 data=None message='Internal error'"
        )
        text = user_facing_llm_error(err).lower()
        self.assertIn("quota", text)
        self.assertIn("api key", text)

    def test_generic(self) -> None:
        err = RuntimeError("connection refused")
        self.assertTrue(user_facing_llm_error(err).startswith("The agent hit an error:"))


if __name__ == "__main__":
    unittest.main()
