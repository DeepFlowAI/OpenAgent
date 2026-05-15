"""
Unit tests for the OpenAgent OpenAPI CLI.
"""
import json

import pytest

from app.openapi_cli import (
    CliError,
    OpenApiClient,
    ENDPOINTS,
    get_endpoint,
    load_json_payload,
    main,
)


class TestOpenApiCliCatalog:
    def test_catalog_has_stable_unique_keys(self) -> None:
        keys = [endpoint.key for endpoint in ENDPOINTS]

        assert len(keys) == len(set(keys))
        assert "knowledge.list" in keys
        assert "chat.stream" in keys
        assert "agents.list" in keys
        assert "channels.secret_key" in keys

    def test_get_endpoint_unknown_key_raises_clear_error(self) -> None:
        with pytest.raises(CliError, match="Unknown endpoint"):
            get_endpoint("missing.endpoint")


class TestOpenApiCliJsonPayload:
    def test_load_json_payload_from_text(self) -> None:
        payload = load_json_payload('{"name":"Support"}', None)

        assert payload == {"name": "Support"}

    def test_load_json_payload_rejects_non_object(self) -> None:
        with pytest.raises(CliError, match="must be an object"):
            load_json_payload("[1, 2, 3]", None)

    def test_load_json_payload_rejects_two_sources(self) -> None:
        with pytest.raises(CliError, match="cannot be used together"):
            load_json_payload("{}", "payload.json")


class TestOpenApiCliClient:
    def test_build_url_formats_path_and_query(self) -> None:
        client = OpenApiClient("http://localhost:5001/", "sk-test")
        endpoint = get_endpoint("knowledge.documents")

        url = client._build_url(
            endpoint,
            {"kb_id": 1},
            {"page": 2, "per_page": 20, "source": None},
        )

        assert url == "http://localhost:5001/api/v1/knowledge-bases/1/documents?page=2&per_page=20"

    def test_missing_api_key_is_rejected_before_request(self) -> None:
        client = OpenApiClient("http://localhost:5001", None)

        with pytest.raises(CliError, match="Missing API key"):
            client.request("agents.list")


class TestOpenApiCliMain:
    def test_docs_list_outputs_machine_readable_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["docs", "list"])

        captured = capsys.readouterr()
        assert exit_code == 0
        payload = json.loads(captured.out)
        assert any(item["key"] == "chat.stream" for item in payload)

    def test_docs_show_json_outputs_endpoint_detail(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["docs", "show", "chat.stream", "--json"])

        captured = capsys.readouterr()
        assert exit_code == 0
        payload = json.loads(captured.out)
        assert payload["method"] == "POST"
        assert payload["scope"] == "chat"
