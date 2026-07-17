"""Unit tests for Open API chat attachment validation."""

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest


def _image(**overrides) -> dict:
    data = {
        "type": "image",
        "url": "https://files.example.com/photo.png?token=secret",
        "name": "photo.png",
        "mime_type": "image/png",
        "size": 128,
    }
    data.update(overrides)
    return data


def test_chat_request_accepts_attachment_without_text():
    request = ChatRequest(attachments=[_image()])

    assert request.message is None
    assert request.attachments[0].name == "photo.png"


def test_chat_request_accepts_text_with_mixed_attachments():
    request = ChatRequest(
        message="请帮我处理",
        attachments=[
            _image(),
            {
                "type": "file",
                "url": "https://files.example.com/contract.pdf",
                "name": "contract.pdf",
                "mime_type": "application/pdf",
                "size": 1024,
            },
        ],
    )

    assert len(request.attachments) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": "   "},
        {"attachments": [_image(url="http://files.example.com/photo.png")]},
        {"attachments": [_image(url="https://files example.com/photo.png")]},
        {"attachments": [_image(mime_type="application/octet-stream")]},
        {"attachments": [_image(size=0)]},
        {
            "attachments": [
                _image(url=f"https://files.example.com/{index}.png")
                for index in range(6)
            ]
        },
    ],
)
def test_chat_request_rejects_invalid_attachment_messages(payload):
    with pytest.raises(ValidationError):
        ChatRequest(**payload)


def test_chat_request_rejects_image_mime_for_file_attachment():
    with pytest.raises(ValidationError):
        ChatRequest(
            attachments=[
                {
                    **_image(),
                    "type": "file",
                }
            ]
        )
