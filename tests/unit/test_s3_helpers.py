# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from lib.charms.mysql.v0.s3_helpers import upload_content_to_s3


class TestS3Helpers(unittest.TestCase):
    def setUp(self) -> None:
        self.s3_parameters = {
            "access-key": "AK",
            "secret-key": "SK",
            "region": "AS-1",
            "bucket": "balde",
            "endpoint": "http://localhost:9000",
        }

    @patch("lib.charms.mysql.v0.s3_helpers.boto3")
    def test_upload_content_without_ca_chain(self, mock_boto):
        mock_session = MagicMock()
        mock_resource = MagicMock()
        mock_bucket = MagicMock()

        mock_boto.session.Session.return_value = mock_session
        mock_session.resource.return_value = mock_resource
        mock_resource.Bucket.return_value = mock_bucket

        upload_content_to_s3("content", "key", self.s3_parameters)

        mock_bucket.upload_file.assert_called_once()
        mock_session.resource.assert_called_with(
            "s3", endpoint_url="http://localhost:9000", verify=True
        )

    @patch("lib.charms.mysql.v0.s3_helpers.boto3")
    def test_upload_content_with_ca_chain(self, mock_boto):
        mock_session = MagicMock()
        mock_resource = MagicMock()
        mock_bucket = MagicMock()

        mock_boto.session.Session.return_value = mock_session
        mock_session.resource.return_value = mock_resource
        mock_resource.Bucket.return_value = mock_bucket

        s3_parameters = {
            "access-key": "AK",
            "secret-key": "SK",
            "region": "AS-1",
            "bucket": "balde",
            "endpoint": "http://localhost:9000",
            "tls-ca-chain": ["Zm9vYmFy"],
        }

        upload_content_to_s3("content", "key", s3_parameters)

        mock_bucket.upload_file.assert_called_once()
        mock_session.resource.assert_called_once()
