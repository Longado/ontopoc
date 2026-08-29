import io
import json
import unittest

from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.recognition import RecognitionError


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OpenAICompatibleGatewayTest(unittest.TestCase):
    def test_posts_json_mode_without_exposing_key_in_body(self) -> None:
        observed: dict[str, object] = {}

        def opener(request: object, timeout: float) -> FakeResponse:
            observed["request"] = request
            observed["timeout"] = timeout
            return FakeResponse(
                {
                    "model": "served-model",
                    "choices": [{"message": {"content": '{"schema":"ok"}'}}],
                }
            )

        gateway = OpenAICompatibleGateway(
            api_base="https://models.example/v1/",
            api_key="secret-value",
            model="configured-model",
            timeout_seconds=12,
            opener=opener,
        )

        completion = gateway.complete_json(
            system_prompt="system",
            user_prompt="user",
        )

        request = observed["request"]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://models.example/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer secret-value")
        self.assertNotIn("secret-value", request.data.decode("utf-8"))
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["model"], "configured-model")
        self.assertEqual(observed["timeout"], 12)
        self.assertEqual(completion.model, "served-model")
        self.assertEqual(completion.content, '{"schema":"ok"}')

    def test_invalid_provider_response_fails_loudly(self) -> None:
        gateway = OpenAICompatibleGateway(
            api_base="https://models.example/v1",
            api_key="secret-value",
            model="configured-model",
            opener=lambda request, timeout: FakeResponse({"choices": []}),
        )

        with self.assertRaisesRegex(RecognitionError, "invalid model response"):
            gateway.complete_json(system_prompt="system", user_prompt="user")

    def test_network_failure_is_wrapped_without_key(self) -> None:
        def failing_opener(request: object, timeout: float) -> object:
            raise OSError("connection refused")

        gateway = OpenAICompatibleGateway(
            api_base="https://models.example/v1",
            api_key="secret-value",
            model="configured-model",
            opener=failing_opener,
        )

        with self.assertRaisesRegex(RecognitionError, "model request failed") as raised:
            gateway.complete_json(system_prompt="system", user_prompt="user")
        self.assertNotIn("secret-value", str(raised.exception))

    def test_invalid_request_url_is_wrapped_as_recognition_error(self) -> None:
        gateway = OpenAICompatibleGateway(
            api_base="https://models.example/invalid\npath",
            api_key="secret-value",
            model="configured-model",
        )

        with self.assertRaisesRegex(RecognitionError, "model request failed") as raised:
            gateway.complete_json(system_prompt="system", user_prompt="user")
        self.assertIs(type(raised.exception), RecognitionError)


if __name__ == "__main__":
    unittest.main()
