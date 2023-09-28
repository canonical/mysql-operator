#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the Kafka charm."""
import configparser
import logging
import os
import re
from typing import Optional

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import validator

from constants import MYSQLD_CUSTOM_CONFIG_FILE

logger = logging.getLogger(__name__)

# Static config requires workload restart
STATIC_CONFIGS = {
    "innodb_buffer_pool_size",
    "innodb_buffer_pool_chunk_size",
    "group_replication_message_cache_size",
}


class StrippedConfigParser(configparser.RawConfigParser):
    """ConfigParser that strips quotes from values.

    Necessary because MySQL config files use quotes around some values.
    """

    def get(self, section, option):
        """Return the value of the named option in the named section."""
        return super().get(section, option).strip('"')


class MySQLConfig:
    """Configuration."""

    @property
    def custom_config(self) -> Optional[dict]:
        """Return current custom config dict."""
        if not os.path.exists(MYSQLD_CUSTOM_CONFIG_FILE):
            return None

        cp = StrippedConfigParser()

        with open(MYSQLD_CUSTOM_CONFIG_FILE, "r") as config_file:
            cp.read_file(config_file)

        return dict(cp["mysqld"])


class CharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    profile: str
    cluster_name: Optional[str]
    profile_limit_memory: Optional[int]
    mysql_interface_user: Optional[str]
    mysql_interface_database: Optional[str]

    @validator("profile")
    @classmethod
    def profile_values(cls, value: str) -> Optional[str]:
        """Check profile config option is one of `testing` or `production`."""
        if value not in ["testing", "production"]:
            raise ValueError("Value not one of 'testing' or 'production'")

        return value

    @validator("cluster_name")
    @classmethod
    def cluster_name_validator(cls, value: str) -> Optional[str]:
        """Check for valid cluster name.

        Limited to 63 characters, and must start with a letter and
        contain only alphanumeric characters, `-`, `_` and `.`
        """
        if len(value) > 63:
            raise ValueError("Cluster name must be less than 63 characters")

        if not value[0].isalpha():
            raise ValueError("Cluster name must start with a letter")

        if not re.match(r"^[a-zA-Z0-9-_.]*$", value):
            raise ValueError(
                "Cluster name must contain only alphanumeric characters, "
                "hyphens, underscores and periods"
            )

        return value

    @validator("profile_limit_memory")
    @classmethod
    def profile_limit_memory_validator(cls, value: int) -> Optional[int]:
        """Check profile limit memory."""
        if value < 600:
            raise ValueError("MySQL Charm requires at least 600MB for bootstrapping")
        if value > 9999999:
            raise ValueError("`profile-limit-memory` limited to 7 digits (9999999MB)")

        return value
