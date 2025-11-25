#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from constants import DB_RELATION_NAME, PASSWORD_LENGTH, ROOT_USERNAME
from utils import generate_random_password

from ... import markers
from ...helpers_ha import (
    CHARM_METADATA,
    MINUTE_SECS,
    check_read_only_endpoints,
    get_app_units,
    get_mysql_primary_unit,
    get_mysql_server_credentials,
    get_relation_data,
    get_unit_ip,
    remove_leader_unit,
    rotate_mysql_server_credentials,
    scale_app_units,
    wait_for_apps_status,
)
from ...helpers_ha import (
    execute_queries_on_unit_sync as execute_queries_on_unit,
)

logger = logging.getLogger(__name__)

DATABASE_APP_NAME = CHARM_METADATA["name"]
CLUSTER_NAME = "test_cluster"

APPLICATION_APP_NAME = "mysql-test-app"

APPS = [DATABASE_APP_NAME, APPLICATION_APP_NAME]

ENDPOINT = "database"
TIMEOUT = 15 * MINUTE_SECS


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
def test_build_and_deploy(juju: Juju, charm):
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    juju.deploy(
        charm,
        DATABASE_APP_NAME,
        config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
        num_units=3,
        base="ubuntu@22.04",
    )
    juju.deploy(
        APPLICATION_APP_NAME,
        num_units=2,
        channel="latest/edge",
        base="ubuntu@22.04",
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, APPLICATION_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_password_rotation(juju: Juju):
    """Rotate password and confirm changes."""
    random_unit = get_app_units(juju, DATABASE_APP_NAME)[-1]

    old_credentials = get_mysql_server_credentials(juju, random_unit)

    # get primary unit first, need that to invoke set-password action
    primary_unit_name = get_mysql_primary_unit(juju, DATABASE_APP_NAME, random_unit)
    primary_unit_address = get_unit_ip(juju, DATABASE_APP_NAME, primary_unit_name)
    logger.debug("Primary unit detected before password rotation is %s", primary_unit_address)

    new_password = generate_random_password(PASSWORD_LENGTH)

    rotate_mysql_server_credentials(juju, primary_unit_name, password=new_password)

    updated_credentials = get_mysql_server_credentials(juju, random_unit)
    assert updated_credentials["password"] != old_credentials["password"]
    assert updated_credentials["password"] == new_password

    # verify that the new password actually works by querying the db
    show_tables_sql = ["SHOW DATABASES"]
    output = execute_queries_on_unit(
        primary_unit_address,
        updated_credentials["username"],
        updated_credentials["password"],
        show_tables_sql,
    )
    assert len(output) > 0, "query with new password failed, no databases found"


@pytest.mark.abort_on_fail
def test_password_rotation_silent(juju: Juju):
    """Rotate password and confirm changes."""
    random_unit = get_app_units(juju, DATABASE_APP_NAME)[-1]

    old_credentials = get_mysql_server_credentials(juju, random_unit)

    # get primary unit first, need that to invoke set-password action
    primary_unit = get_mysql_primary_unit(juju, DATABASE_APP_NAME, random_unit)
    primary_unit_address = get_unit_ip(juju, DATABASE_APP_NAME, primary_unit)
    logger.debug("Primary unit detected before password rotation is %s", primary_unit_address)

    rotate_mysql_server_credentials(juju, primary_unit)

    updated_credentials = get_mysql_server_credentials(juju, random_unit)
    assert updated_credentials["password"] != old_credentials["password"]

    # verify that the new password actually works by querying the db
    show_tables_sql = ["SHOW DATABASES"]
    output = execute_queries_on_unit(
        primary_unit_address,
        updated_credentials["username"],
        updated_credentials["password"],
        show_tables_sql,
    )
    assert len(output) > 0, "query with new password failed, no databases found"


@pytest.mark.abort_on_fail
def test_password_rotation_root_user(juju: Juju):
    """Rotate password for root user and confirm changes."""
    random_unit = get_app_units(juju, DATABASE_APP_NAME)[-1]

    old_credentials = get_mysql_server_credentials(juju, random_unit, ROOT_USERNAME)

    # get primary unit first, need that to invoke set-password action
    primary_unit = get_mysql_primary_unit(juju, DATABASE_APP_NAME, random_unit)
    primary_unit_address = get_unit_ip(juju, DATABASE_APP_NAME, primary_unit)
    logger.debug("Primary unit detected before password rotation is %s", primary_unit_address)

    rotate_mysql_server_credentials(juju, primary_unit, ROOT_USERNAME)

    updated_credentials = get_mysql_server_credentials(juju, random_unit, ROOT_USERNAME)
    assert updated_credentials["password"] != old_credentials["password"]


@pytest.mark.abort_on_fail
@markers.only_without_juju_secrets
def test_relation_creation_databag(juju: Juju):
    """Relate charms and wait for the expected changes in status."""
    juju.integrate(f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APPLICATION_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )

    relation_data = get_relation_data(juju, APPLICATION_APP_NAME, DB_RELATION_NAME)
    assert {"password", "username"} <= set(relation_data[0]["application-data"])


@pytest.mark.abort_on_fail
@markers.only_with_juju_secrets
def test_relation_creation(juju: Juju):
    """Relate charms and wait for the expected changes in status (using juju secrets)."""
    juju.integrate(f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APPS),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )

    relation_data = get_relation_data(juju, APPLICATION_APP_NAME, DB_RELATION_NAME)
    assert not {"password", "username"} <= set(relation_data[0]["application-data"])
    assert "secret-user" in relation_data[0]["application-data"]


@pytest.mark.abort_on_fail
def test_read_only_endpoints(juju: Juju):
    """Check read-only-endpoints are correctly updated."""
    relation_data = get_relation_data(juju, DATABASE_APP_NAME, DB_RELATION_NAME)
    assert len(relation_data) == 1

    check_read_only_endpoints(juju, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME)

    # increase the number of units
    scale_app_units(juju, DATABASE_APP_NAME, 4)
    check_read_only_endpoints(juju, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME)

    # decrease the number of units
    scale_app_units(juju, DATABASE_APP_NAME, 2)

    # wait for the update of the endpoints
    juju.wait(
        ready=lambda: check_read_only_endpoints(
            juju, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
        )
        or True,
        timeout=5 * MINUTE_SECS,
    )

    # increase the number of units
    scale_app_units(juju, DATABASE_APP_NAME, 3)

    # remove the leader unit
    remove_leader_unit(juju, application_name=DATABASE_APP_NAME)

    # wait for the update of the endpoints
    juju.wait(
        ready=lambda: check_read_only_endpoints(
            juju, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
        )
        or True,
        timeout=5 * MINUTE_SECS,
    )


@pytest.mark.abort_on_fail
def test_relation_broken(juju: Juju):
    """Remove relation and wait for the expected changes in status."""
    juju.remove_relation(f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, APPLICATION_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
