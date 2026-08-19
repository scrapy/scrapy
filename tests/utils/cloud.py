from __future__ import annotations

from typing import Any
from unittest import mock


def mock_google_cloud_storage() -> tuple[Any, Any, Any]:
    """Creates autospec mocks for google-cloud-storage Client, Bucket and Blob
    classes and set their proper return values.
    """
    from google.cloud.storage import Blob, Bucket, Client  # noqa: PLC0415

    client_mock = mock.create_autospec(Client)

    bucket_mock = mock.create_autospec(Bucket)
    client_mock.bucket.return_value = bucket_mock

    blob_mock = mock.create_autospec(Blob)
    bucket_mock.blob.return_value = blob_mock

    return (client_mock, bucket_mock, blob_mock)


def mock_google_cloud_storage_blobs() -> tuple[Any, Any, dict[str, Any]]:
    """Like :func:`mock_google_cloud_storage`, but ``Bucket.blob()`` returns a
    separate Blob mock for each object name, and ``Bucket.get_blob()`` returns
    ``None`` unless configured otherwise.

    Blob mocks are returned in a dict indexed by object name.
    """
    from google.cloud.storage import Bucket, Client  # noqa: PLC0415

    client_mock = mock.create_autospec(Client)

    bucket_mock = mock.create_autospec(Bucket)
    client_mock.bucket.return_value = bucket_mock

    blob_mocks: dict[str, Any] = {}

    def blob(blob_name: str, *args: Any, **kwargs: Any) -> Any:
        if blob_name not in blob_mocks:
            blob_mocks[blob_name] = mock_google_cloud_storage_blob(name=blob_name)
        return blob_mocks[blob_name]

    bucket_mock.blob.side_effect = blob
    bucket_mock.get_blob.return_value = None

    return (client_mock, bucket_mock, blob_mocks)


def mock_google_cloud_storage_blob(**properties: Any) -> Any:
    """Creates an autospec mock for the google-cloud-storage Blob class with
    the given properties, e.g. ``name`` or ``content_type``.
    """
    from google.cloud.storage import Blob  # noqa: PLC0415

    blob_mock = mock.create_autospec(Blob)
    for name, value in properties.items():
        setattr(blob_mock, name, value)
    return blob_mock
