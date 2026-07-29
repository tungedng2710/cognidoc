import pytest
from data_studio_api.schemas import DatasetCreate
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ("License plate", "license-plate"),
        ("  License   plate  ", "license-plate"),
        ("License--plate", "license-plate"),
        ("DATASET.v2", "dataset.v2"),
    ],
)
def test_dataset_create_normalizes_slug(provided: str, expected: str) -> None:
    dataset = DatasetCreate(namespace="owner", slug=provided)

    assert dataset.slug == expected


def test_dataset_create_still_rejects_unsupported_slug_characters() -> None:
    with pytest.raises(ValidationError):
        DatasetCreate(namespace="owner", slug="License/plate")
