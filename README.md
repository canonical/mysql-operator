# Charmed MySQL VM operator

## Description

This repository contains a [Juju Charm](https://charmhub.io/mysql) for deploying [MySQL](https://www.mysql.com/) on virtual machines ([LXD](https://ubuntu.com/lxd)).
To deploy on Kubernetes, please use [Charmed MySQL K8s operator](https://charmhub.io/mysql-k8s).

## Usage

To deploy this charm using Juju 2.9 or later, run:

```shell
juju add-model my-model
juju deploy mysql --channel edge
```

**Note:** the above model must be created on LXD (virtual machines) environment. Use [another](https://charmhub.io/mysql-k8s) charm for K8s!

To confirm the deployment, you can run:

```shell
juju status --watch 1s
```

Once MySQL starts up, it will be running on the default port (3306).
Please follow the [tutorial guide](https://discourse.charmhub.io/t/charmed-mysql-tutorial/8623) with detailed explanation how to access DB, configure cluster, change credentials and/or enable TLS.

If required, you can remove the deployment completely by running:

```shell
juju destroy-model my-model --destroy-storage --yes
```

**Note:** the `--destroy-storage` will delete any data persisted by MySQL.

## Relations

### Modern relations

This charm implements the [provides data platform library](https://charmhub.io/data-platform-libs/libraries/database_provides), with the modern `mysql_client` interface.
To relate to it, use the [requires data-platform library](https://charmhub.io/data-platform-libs/libraries/database_requires).

Adding a relation is accomplished with:

```shell
# Deploy MySQL cluster with 3 nodes
juju deploy mysql -n 3 --channel edge
# Deploy the relevant charms
juju deploy mycharm
# Relate mysql with mycharm
juju relate mysql mycharm
```

**Note:** In order to relate with this charm, every table created by the related application must have a primary key. This is required by the [group replication plugin](https://dev.mysql.com/doc/refman/5.7/en/group-replication-requirements.html), enable in this charm.


### Legacy relations

**Note:** Legacy relations are deprecated and will be discontinued on future releases. Usage should be avoided.

This charm supports several legacy interfaces, e.g. `db-router`, `shared-db` and `mysql`:

1. `db-router` is a relation that one uses with the [mysql router](https://charmhub.io/mysql-router) charm. The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel edge
juju deploy mysql-router --series focal
juju deploy keystone --series focal
juju relate mysql-router keystone
juju relate mysql:db-router mysql-router:db-router
```

**Note:** pay attention to deploy identical [series](https://juju.is/docs/olm/deploy-an-application-with-a-specific-series) for `keystone` and `mysql-router` applications (due to the [subordinate](https://juju.is/docs/sdk/charm-types#heading--subordinate-charms) charm nature of `mysql-router`).

2. `shared-db` is a relation that one uses when the application needs to connect directly to the database cluster.
It is supported by various legacy charms, e.g. [mysql-innodb-cluster](https://charmhub.io/mysql-innodb-cluster).
The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel edge
juju deploy keystone --series focal
juju relate keystone:shared-db mysql:shared-db
```

3. `mysql` is a relation that's used from some k8s charms and can be used in cross-model relations.

```shell
juju deploy mysql --channel edge
juju deploy mediawiki
juju relate mysql:mysql mediawiki:db
```

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License
The Charmed MySQL VM Operator [is distributed](https://github.com/canonical/mysql-operator/blob/main/LICENSE) under the Apache Software License, version 2.0.
It installs/operates/depends on [MySQL Community Edition](https://github.com/mysql/mysql-server), which [is licensed](https://github.com/mysql/mysql-server/blob/8.0/LICENSE) under the GPL License, version 2.

## Trademark Notice
MySQL is a trademark or registered trademark of Oracle America, Inc.
Other trademarks are property of their respective owners.

