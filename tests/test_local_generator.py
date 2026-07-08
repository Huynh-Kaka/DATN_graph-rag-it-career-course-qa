from unittest.mock import MagicMock, patch

from app.services.local_generator_client import LocalGeneratorClient


@patch("app.services.local_generator_client.httpx.Client")
def test_local_generate(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.return_value.status_code = 200
    mock_client.post.return_value.json.return_value = {
        "message": {"content": "Xin chào từ Ollama"}
    }

    client = LocalGeneratorClient()
    assert client.available is True
    text = client.generate(
        system_prompt="sys",
        user_prompt="user",
        intent="pathfinding",
    )
    assert "Ollama" in text
