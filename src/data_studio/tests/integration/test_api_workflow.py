from data_studio_api.config import get_settings
from fastapi.testclient import TestClient


def _create_repository(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets",
        json={
            "namespace": "research",
            "slug": "sentiment",
            "visibility": "internal",
            "description": "Small sentiment fixture",
        },
    )
    assert response.status_code == 201, response.text


def _upload_fixture(client: TestClient) -> dict:
    create = client.post(
        "/api/v1/datasets/research/sentiment/uploads",
        json={"commit_message": "Import Hugging Face folder"},
    )
    assert create.status_code == 201, create.text
    upload_id = create.json()["id"]
    card = b"""---
license: mit
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train-*.jsonl
      - split: test
        path: data/test.jsonl
---
# Sentiment demo

Rows uploaded without conversion.
"""
    train = (
        b'{"text":"excellent","label":1,"meta":{"lang":"en"}}\n'
        b'{"text":"bad","label":0,"meta":{"lang":"en"}}\n'
    )
    test = b'{"text":"fine","label":1,"meta":{"lang":"en"}}\n'
    files = [
        ("files", ("README.md", card, "text/markdown")),
        ("files", ("train.jsonl", train, "application/x-ndjson")),
        ("files", ("test.jsonl", test, "application/x-ndjson")),
        ("paths", (None, "README.md")),
        ("paths", (None, "data/train-00000-of-00001.jsonl")),
        ("paths", (None, "data/test.jsonl")),
    ]
    uploaded = client.post(f"/api/v1/uploads/{upload_id}/files", files=files)
    assert uploaded.status_code == 200, uploaded.text
    complete = client.post(f"/api/v1/uploads/{upload_id}/complete", json={"expected_file_count": 3})
    assert complete.status_code == 200, complete.text
    return {"revision": complete.json(), "train": train}


def test_upload_to_viewer_and_byte_identical_download(client: TestClient) -> None:
    _create_repository(client)
    uploaded = _upload_fixture(client)
    revision = uploaded["revision"]

    assert revision["status"] == "ready"
    assert revision["card_metadata"]["license"] == "mit"
    assert [config["name"] for config in revision["configs"]] == ["default"]
    assert {split["name"] for split in revision["configs"][0]["splits"]} == {"train", "test"}

    viewer = client.get(
        "/api/v1/datasets/research/sentiment/viewer/default/train",
        params={"revision": revision["revision_id"], "limit": 1},
    )
    assert viewer.status_code == 200, viewer.text
    assert viewer.json()["rows"] == [{"text": "excellent", "label": 1, "meta": {"lang": "en"}}]
    assert viewer.json()["capabilities"]["preview_is_bounded"] is True

    download = client.get(
        f"/api/v1/datasets/research/sentiment/blob/{revision['revision_id']}/"
        "data/train-00000-of-00001.jsonl"
    )
    assert download.status_code == 200
    assert download.content == uploaded["train"]
    assert download.headers["content-disposition"].startswith("attachment;")

    inline = client.get(
        f"/api/v1/datasets/research/sentiment/blob/{revision['revision_id']}/"
        "data/train-00000-of-00001.jsonl",
        params={"inline": True},
    )
    assert inline.headers["content-disposition"].startswith("inline;")

    dataset = client.get("/api/v1/datasets/research/sentiment").json()
    assert dataset["latest_revision"]["revision_id"] == revision["revision_id"]


def test_retrying_same_tree_is_idempotent(client: TestClient) -> None:
    _create_repository(client)
    first = _upload_fixture(client)["revision"]
    second = _upload_fixture(client)["revision"]

    assert second["revision_id"] == first["revision_id"]
    revisions = client.get("/api/v1/datasets/research/sentiment/revisions").json()
    assert len(revisions) == 1


def test_role_boundary_blocks_reader_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets",
        json={"namespace": "research", "slug": "blocked"},
        headers={"X-Data-Studio-Role": "reader"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_zero_upload_limits_disable_resource_caps(client: TestClient) -> None:
    settings = get_settings()
    original = (
        settings.max_upload_bytes,
        settings.max_file_bytes,
        settings.max_file_count,
    )
    settings.max_upload_bytes = 0
    settings.max_file_bytes = 0
    settings.max_file_count = 0
    try:
        _create_repository(client)
        revision = _upload_fixture(client)["revision"]
        assert revision["status"] == "ready"
    finally:
        (
            settings.max_upload_bytes,
            settings.max_file_bytes,
            settings.max_file_count,
        ) = original
