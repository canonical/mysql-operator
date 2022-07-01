# MySQL Machine Charmed Operator

## Description

The [MySQL](https://www.mysql.com/) operator provides an open-source relational database management system (RDBMS). This repository contains a Juju Charm for deploying MySQL on machines.

This charm is currently in development, with High Availability via Group Replication as a short-term goal.

## Usage

To deploy this charm using Juju 2.9.0 or later, run:

```shell
juju add-model mysql
charmcraft pack
juju deploy ./mysql_ubuntu-20.04-amd64.charm mysql
```

Note: the above model must exist outside of a k8s environment (you could bootstrap an lxd environment).

To confirm the deployment, you can run:

```shell
juju status --color
```

Once MySQL starts up, it will be running on the default port (3306).

If required, you can remove the deployment completely by running:

```shell
juju destroy-model -y mysql --destroy-storage
```

Note: the `--destroy-storage` will delete any data persisted by MySQL.

## Relations

We have added support for two legacy relations (from the [mysql-innodb-cluster](https://charmhub.io/mysql-innodb-cluster) charm):

1. `db-router` is a relation that one uses with the [mysql router](https://charmhub.io/mysql-router) charm. The following commands can be executed to deploy and relate to the keystone charm:

```shell
# Pack the charm
charmcraft pack

# Deploy the relevant charms
juju deploy -n 3 ./mysql_ubuntu-20.04-amd64.charm mysql
juju deploy keystone
juju deploy mysql-router keystone-mysql-router

# Relate mysql-router with keystone
juju relate keystone:shared-db keystone-mysql-router:shared-db

# Relate mysql-router with mysql
juju relate keystone-mysql-router:db-router mysql:db-router
```

1. `shared-db` is a relation that one uses when the application needs to connect directly to the database cluster. The following commands can be executed to deploy and relate to the keystone charm:

```shell
# Pack the charm
charmcraft pack

# Deploy the relevant charms
juju deploy -n 3 ./mysql_ubuntu-20.04-amd64.charm mysql
juju deploy keystone

# Relate keystone with mysql
juju relate keystone:shared-db mysql:shared-db
```

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer
guidance.
