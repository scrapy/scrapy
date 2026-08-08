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
    client_mock.get_bucket.return_value = bucket_mock

    blob_mock = mock.create_autospec(Blob)
    bucket_mock.blob.return_value = blob_mock

    return (client_mock, bucket_mock, blob_mock)
