#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the MySQL charm."""

import configparser
import logging
import os
import re

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from charms.mysql.v0.mysql import MAX_CONNECTIONS_FLOOR
from pydantic import validator

logger = logging.getLogger(__name__)


class MySQLConfig:
    """Configuration."""

    # Static config requires workload restart
    static_config = {
        "innodb_buffer_pool_size",
        "innodb_buffer_pool_chunk_size",
        "group_replication_message_cache_size",
        "log_error",
        "loose-audit_log_strategy",
        "loose-audit_log_format",
        "admin_address",
    }

    def __init__(self, config_file_path: str):
        """Initialize config."""
        self.config_file_path = config_file_path

    def keys_requires_restart(self, keys: set) -> bool:
        """Check if keys require restart."""
        return bool(keys & self.static_config)

    def filter_static_keys(self, keys: set) -> set:
        """Filter static keys."""
        return keys - self.static_config

    @property
    def custom_config(self) -> dict | None:
        """Return current custom config dict."""
        if not os.path.exists(self.config_file_path):
            return None

        cp = configparser.ConfigParser(interpolation=None)

        with open(self.config_file_path, "r") as config_file:
            cp.read_file(config_file)

        return dict(cp["mysqld"])


class CharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    profile: str
    cluster_name: str | None
    cluster_set_name: str | None
    profile_limit_memory: int | None
    mysql_interface_user: str | None
    mysql_interface_database: str | None
    experimental_max_connections: int | None
    binlog_retention_days: int
    plugin_audit_enabled: bool
    plugin_audit_strategy: str
    logs_audit_policy: str
    logs_retention_period: str

    @validator("profile")
    @classmethod
    def profile_values(cls, value: str) -> str | None:
        """Check profile config option is one of `testing` or `production`."""
        if value not in ["testing", "production"]:
            raise ValueError("Value not one of 'testing' or 'production'")

        return value

    @validator("cluster_name", "cluster_set_name")
    @classmethod
    def cluster_name_validator(cls, value: str) -> str | None:
        """Check for valid cluster, cluster-set name.

        Limited to 63 characters, and must start with a letter and
        contain only alphanumeric characters, `-`, `_` and `.`
        """
        if len(value) > 63:
            raise ValueError("cluster, cluster-set name must be less than 63 characters")

        if not value[0].isalpha():
            raise ValueError("cluster, cluster-set name must start with a letter")

        if not re.match(r"^[a-zA-Z0-9-_.]*$", value):
            raise ValueError(
                "cluster, cluster-set name must contain only alphanumeric characters, "
                "hyphens, underscores and periods"
            )

        return value

    @validator("profile_limit_memory")
    @classmethod
    def profile_limit_memory_validator(cls, value: int) -> int | None:
        """Check profile limit memory."""
        if value < 600:
            raise ValueError("MySQL Charm requires at least 600MB for bootstrapping")
        if value > 9999999:
            raise ValueError("`profile-limit-memory` limited to 7 digits (9999999MB)")

        return value

    @validator("experimental_max_connections")
    @classmethod
    def experimental_max_connections_validator(cls, value: int) -> int | None:
        """Check experimental max connections."""
        if value < MAX_CONNECTIONS_FLOOR:
            raise ValueError(
                f"experimental-max-connections ({value=}) must be equal or greater "
                + f" than {MAX_CONNECTIONS_FLOOR}"
            )

        return value

    @validator("binlog_retention_days")
    @classmethod
    def binlog_retention_days_validator(cls, value: int) -> int:
        """Check binlog retention days."""
        if value < 1:
            raise ValueError("binlog-retention-days must be greater than 0")

        return value

    @validator("plugin_audit_strategy")
    @classmethod
    def plugin_audit_strategy_validator(cls, value: str) -> str | None:
        """Check profile config option is one of `testing` or `production`."""
        if value not in ["async", "semi-async"]:
            raise ValueError("Value not one of 'async' or 'semi-async'")

        return value

    @validator("logs_audit_policy")
    @classmethod
    def logs_audit_policy_validator(cls, value: str) -> str | None:
        """Check values for audit log policy."""
        valid_values = ["all", "logins", "queries"]
        if value not in valid_values:
            raise ValueError(f"logs_audit_policy not one of {', '.join(valid_values)}")

        return value

    @validator("logs_retention_period")
    @classmethod
    def logs_retention_period_validator(cls, value: str) -> str:
        """Check logs retention period."""
        if (value.isalpha() and value != "auto") or (value.isdigit() and int(value) < 3):
            raise ValueError("logs_retention_period must be >= 3 or `auto`")

        return value
