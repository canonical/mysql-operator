# Charmed MySQL VM operator
[![CharmHub Badge](https://charmhub.io/mysql/badge.svg)](https://charmhub.io/mysql)
[![Release](https://github.com/canonical/mysql-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/mysql-operator/actions/workflows/release.yaml)
[![Tests](https://github.com/canonical/mysql-operator/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/canonical/mysql-operator/actions/workflows/ci.yaml?query=branch%3Amain)

## Description

This repository contains a [Juju Charm](https://charmhub.io/mysql) for deploying [MySQL](https://www.mysql.com/) on [virtual machines](https://ubuntu.com/lxd).

To deploy on [Kubernetes](https://microk8s.io/), please use [Charmed MySQL K8s operator](https://charmhub.io/mysql-k8s).

## Usage

To deploy this charm using Juju 2.9 or later, run:

```shell
juju add-model mysql-vm
juju deploy mysql --channel 8.0
```

**Note:** the above model must be created on LXD (virtual machines) environment. Use [another](https://charmhub.io/mysql-k8s) charm for K8s!

To confirm the deployment, you can run:

```shell
juju status --watch 1s
```

Once MySQL starts up, it will be running on the default port (3306).

If required, you can remove the deployment completely by running:

```shell
juju destroy-model mysql-vm --destroy-storage --yes
```

**Note:** the `--destroy-storage` will delete any data persisted by MySQL.

## Documentation

Please follow the [tutorial guide](https://discourse.charmhub.io/t/charmed-mysql-tutorial/8623) with detailed explanation how to access DB, configure cluster, change credentials and/or enable TLS.

## Integrations ([relations](https://juju.is/docs/olm/relations))

The charm supports modern `mysql_client` and legacy `mysql`, `mysql-shared`, `mysql-router` interfaces (in a backward compatible mode).

**Note:** do NOT relate both modern and legacy interfaces simultaneously!

### Modern interfaces

This charm implements the [provides data platform library](https://charmhub.io/data-platform-libs/libraries/database_provides), with the modern `mysql_client` interface.
To relate to it, use the [requires data-platform library](https://charmhub.io/data-platform-libs/libraries/database_requires).

#### Modern `mysql_client` interface (`database` endpoint):

Adding a relation is accomplished with `juju relate` (or `juju integrate` for Juju 3.x) via endpoint `database`. Example:

```shell
# Deploy Charmed MySQL cluster with 3 nodes
juju deploy mysql -n 3 --channel 8.0

# Deploy the relevant charms, e.g. mysql-test-app
juju deploy mysql-test-app

# Relate MySQL with your application
juju relate mysql:database mysql-test-app:database

# Check established relation (using mysql_client interface):
juju status --relations

# Example of the properly established relation:
# > Relation provider   Requirer                 Interface     Type
# > mysql:database      mysql-test-app:database  mysql_client  regular
```

**Note:** In order to relate with this charm, every table created by the related application must have a primary key. This is required by the [group replication plugin](https://dev.mysql.com/doc/refman/8.0/en/group-replication-requirements.html) enabled in this charm.

### Legacy interfaces

**Note:** Legacy relations are deprecated and will be discontinued on future releases. Usage should be avoided.

This charm supports several legacy interfaces, e.g. `mysql`, `mysql-shared`, `mysql-router`. They were used in some legacy charms in [cross-model relations](https://juju.is/docs/olm/cross-model-integration).

#### Legacy `mysql` interface (`mysql` endpoint)

It was a popular interface used by some legacy charms (e.g. "[MariaDB](https://charmhub.io/mariadb)", "[OSM MariaDB](https://charmhub.io/charmed-osm-mariadb-k8s)", "[Percona Cluster](https://charmhub.io/percona-cluster)" and "[Mysql Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)"), often in [cross-model relations](https://juju.is/docs/olm/cross-model-integration):

```shell
juju deploy mysql --channel 8.0
juju config mysql mysql-interface-database=mediawiki mysql-interface-user=mediawiki
juju deploy mediawiki
juju relate mysql:mysql mediawiki:db
```

#### `mysql-router` interface (`db-router` endpoint)

It is a relation that one uses with the [mysql router](https://charmhub.io/mysql-router) charm. The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel 8.0
juju deploy mysql-router --series focal
juju deploy keystone --series focal
juju relate mysql-router keystone
juju relate mysql:db-router mysql-router:db-router
```

**Note:** pay attention to deploy identical [series](https://juju.is/docs/olm/deploy-an-application-with-a-specific-series) for `keystone` and `mysql-router` applications (due to the [subordinate](https://juju.is/docs/sdk/charm-types#heading--subordinate-charms) charm nature of `mysql-router`).

#### `mysql-shared` interface (`shared-db` endpoint)

It is a relation that one uses when the application needs to connect directly to the database cluster.
It is supported by various legacy charms, e.g. [mysql-innodb-cluster](https://charmhub.io/mysql-innodb-cluster).
The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel 8.0
juju deploy keystone --series focal
juju relate keystone:shared-db mysql:shared-db
```

## Security
Security issues in the Charmed MySQL VM Operator can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing
Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License
The Charmed MySQL VM Operator [is distributed](https://github.com/canonical/mysql-operator/blob/main/LICENSE) under the Apache Software License, version 2.0.
It installs/operates/depends on [MySQL Community Edition](https://github.com/mysql/mysql-server), which [is licensed](https://github.com/mysql/mysql-server/blob/8.0/LICENSE) under the GPL License, version 2.

## Trademark Notice
MySQL is a trademark or registered trademark of Oracle America, Inc.
Other trademarks are property of their respective owners.
