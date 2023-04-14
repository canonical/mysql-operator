# Charmed MySQL VM operator

## Description

This repository contains a [Juju Charm](https://charmhub.io/mysql) for deploying [MySQL](https://www.mysql.com/) on [virtual machines](https://ubuntu.com/lxd).

To deploy on [Kubernetes](https://microk8s.io/), please use [Charmed MySQL K8s operator](https://charmhub.io/mysql-k8s).

## Usage

To deploy this charm using Juju 2.9 or later, run:

```shell
juju add-model mysql-vm
juju deploy mysql
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

## Relations

The charm supports modern `mysql_client` and legacy `mysql`, `mysql-shared`, `mysql-router` interfaces (in a backward compatible mode).

**Note:** do NOT relate both modern and legacy interfaces simultaneously.


### Modern relations

This charm implements the [provides data platform library](https://charmhub.io/data-platform-libs/libraries/database_provides), with the modern `mysql_client` interface.
To relate to it, use the [requires data-platform library](https://charmhub.io/data-platform-libs/libraries/database_requires).

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

**Note:** In order to relate with this charm, every table created by the related application must have a primary key. This is required by the [group replication plugin](https://dev.mysql.com/doc/refman/5.7/en/group-replication-requirements.html), enable in this charm.


### Legacy relations

**Note:** Legacy relations are deprecated and will be discontinued on future releases. Usage should be avoided.

This charm supports several legacy interfaces, e.g. `mysql`, `mysql-shared`, `mysql-router`:

1. `mysql` is a relation that's used from some k8s charms and can be used in cross-model relations.

```shell
juju deploy mysql --channel 8.0
juju deploy mediawiki
juju relate mysql:mysql mediawiki:db
```

2. `mysql-router` interface (`db-router` endpoint) is a relation that one uses with the [mysql router](https://charmhub.io/mysql-router) charm. The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel 8.0
juju deploy mysql-router --series focal
juju deploy keystone --series focal
juju relate mysql-router keystone
juju relate mysql:db-router mysql-router:db-router
```

**Note:** pay attention to deploy identical [series](https://juju.is/docs/olm/deploy-an-application-with-a-specific-series) for `keystone` and `mysql-router` applications (due to the [subordinate](https://juju.is/docs/sdk/charm-types#heading--subordinate-charms) charm nature of `mysql-router`).

3. `mysql-shared` interface (`shared-db` endpoint) is a relation that one uses when the application needs to connect directly to the database cluster.
It is supported by various legacy charms, e.g. [mysql-innodb-cluster](https://charmhub.io/mysql-innodb-cluster).
The following commands can be executed to deploy and relate to the keystone charm:

```shell
juju deploy mysql --channel 8.0
juju deploy keystone --series focal
juju relate keystone:shared-db mysql:shared-db
```

## Monitoring

The Charmed MySQL Operator comes with several exporters by default. The metrics can be queried by accessing the following endpoints:

- MySQL exporter: `http://<unit-ip>:9104/metrics`

Additionally, the charm provides integration with the [Canonical Observability Stack](https://charmhub.io/topics/canonical-observability-stack).

Deploy `cos-lite` bundle in a Kubernetes environment. This can be done by following the [deployment tutorial](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s). Since the Charmed MySQL Operator is deployed on a machine environment, it is needed to offer the endpoints of the COS relations. The [offers-overlay](https://github.com/canonical/cos-lite-bundle/blob/main/overlays/offers-overlay.yaml) can be used, and this step is shown on the COS tutorial.

Once COS is deployed, we can find the offers from the mysql model:
```shell
# We are on the Kubernetes controller, for the cos model. Switch to mysql model
juju switch <machine_controller_name>:<mysql_model_name>

juju find-offers <k8s_controller_name>:
```

A similar output should appear, if `micro` is the k8s controller name and `cos` the model where `cos-lite` has been deployed:
```
Store        URL                                        Access  Interfaces
<k8s_cos>    admin/cos.grafana-dashboards               admin   grafana_dashboard:grafana-dashboard
<k8s_cos>    admin/cos.loki-logging                     admin   loki_push_api:logging
<k8s_cos>    admin/cos.prometheus-receive-remote-write  admin   prometheus-receive-remote-write:receive-remote-write
. . .
```

Now, deploy `grafana-agent` (subordinate charm) and relate it with charm `mysql`, later relate `grafana-agent` with offered COS relations:
```shell
juju deploy grafana-agent
juju relate mysql:cos-agent grafana-agent
juju relate grafana-agent grafana-dashboards
juju relate grafana-agent loki-logging
juju relate grafana-agent prometheus-receive-remote-write
```

After this is complete, Grafana will show the new dashboards: `MySQL Exporter` and allows access for Charmed MySQL logs on Loki.


## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License
The Charmed MySQL VM Operator [is distributed](https://github.com/canonical/mysql-operator/blob/main/LICENSE) under the Apache Software License, version 2.0.
It installs/operates/depends on [MySQL Community Edition](https://github.com/mysql/mysql-server), which [is licensed](https://github.com/mysql/mysql-server/blob/8.0/LICENSE) under the GPL License, version 2.

## Trademark Notice
MySQL is a trademark or registered trademark of Oracle America, Inc.
Other trademarks are property of their respective owners.
