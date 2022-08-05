# MySQL Machine Charmed Operator

## Description

The [MySQL](https://www.mysql.com/) operator provides an open-source relational database management system (RDBMS). This repository contains a Juju Charm for deploying MySQL on machines.

## Usage

To deploy this charm using Juju 2.9.0 or later, run:

```shell
juju add-model my-model
juju deploy mysql --channel=edge -n 3
```

Note: the above model must exist outside of a k8s environment (you could bootstrap an lxd environment).

To confirm the deployment, you can run:

```shell
juju status --color
```

Once MySQL starts up, it will be running on the default port (3306).

If required, you can remove the deployment completely by running:

```shell
juju destroy-model -y my-model --destroy-storage
```

Note: the `--destroy-storage` will delete any data persisted by MySQL.

## Relations

This charm implements the [provides data platform library](https://charmhub.io/data-platform-libs/libraries/database_provides), with the `mysql_client` interface.
To relate to it, use the [requires data-platform library](https://charmhub.io/data-platform-libs/libraries/database_requires).

Adding a relation is accomplished with:

```shell
# Deploy the relevant charms
juju deploy -n 3 mysql --channel edge
juju deploy mycharm
# Relate mysql-router with keystone
juju relate mycharm:database mysql:database
```

**NOTE:** In order to relate with this charm, every table created by the related
application must have a primary key. This is required by the [group replication
plugin](https://dev.mysql.com/doc/refman/5.7/en/group-replication-requirements.html),
enable in this charm.


### Legacy relations

**NOTE:** Legacy relations are deprecated and will be discontinued on future
releases. Usage should be avoided.

This charm supports two legacy relations (from the [mysql-innodb-cluster](https://charmhub.io/mysql-innodb-cluster) charm).

1. `db-router` is a relation that one uses with the [mysql router](https://charmhub.io/mysql-router) charm. The following commands can be executed to deploy and relate to the keystone charm:

```shell
# Deploy the relevant charms
juju deploy -n 3 mysql --channel edge
juju deploy keystone
juju deploy mysql-router keystone-mysql-router

# Relate mysql-router with keystone
juju relate keystone:shared-db keystone-mysql-router:shared-db

# Relate mysql-router with mysql
juju relate keystone-mysql-router:db-router mysql:db-router
```

2. `shared-db` is a relation that one uses when the application needs to connect directly to the database cluster. The following commands can be executed to deploy and relate to the keystone charm:

```shell
# Deploy the relevant charms
juju deploy -n 3 mysql --channel edge
juju deploy keystone

# Relate keystone with mysql
juju relate keystone:shared-db mysql:shared-db
```

3. `mysql` is a relation that's used from some k8s charms and can be used in cross-model relations.



## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer
guidance.
