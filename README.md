# MySQL Machine Charmed Operator

## Description

The [MySQL](https://www.mysql.com/) operator provides an open-source relational database management system (RDBMS). This repository contains a Juju Charm for deploying MySQL on machines.

This charm is currently in development, with High Availability via Group Replication as a short-term goal.

## Usage

To deploy this charm using Juju 2.9.0 or later, run:

```shell
juju add-model mysql-k8s
juju deploy mysql-k8s
```

To confirm the deployment, you can run:

```shell
juju status --color
```

Once MySQL starts up, it will be running on the default port (3306).

If required, you can remove the deployment completely by running:

```shell
juju destroy-model -y mysql-k8s --destroy-storage
```

Note: the `--destroy-storage` will delete any data persisted by MySQL.

## Relations

There are no relations implemented yet.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer
guidance.
