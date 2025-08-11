# Architecture

[MySQL](https://www.mysql.com/) is the world’s most popular open source database. The "[Charmed MySQL](https://charmhub.io/mysql)" is a Juju-based operator to deploy and support MySQL from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/), it is based on the [MySQL Community Edition](https://www.mysql.com/products/community/) using the built-in cluster functionality: [MySQL InnoDB ClusterSet](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-clusterset.html).

## HLD (High Level Design)

The charm design leverages on the SNAP “[charmed-mysql](https://snapcraft.io/charmed-mysql)” which is deployed by Juju on the specified VM/MAAS/bare-metal machine based on Ubuntu Jammy/22.04. SNAP allows to run MySQL service(s) in a secure and isolated environment ([strict confinement](https://ubuntu.com/blog/demystifying-snap-confinement)). The installed SNAP:
```
> juju ssh mysql/0
> snap list charmed-mysql
Name           Version  Rev  Tracking       Publisher        Notes
charmed-mysql  8.0.34   69   latest/stable  dataplatformbot  held
```

The SNAP ships the following components:

* MySQL Community Edition (based on Ubuntu APT package "[mysql-server-8.0](https://packages.ubuntu.com/jammy/mysql-server-8.0)") 
* MySQL Router (based on Ubuntu APT package "[mysql-router](https://packages.ubuntu.com/jammy/mysql-router)")
* MySQL Shell (based on Canonical [backport](https://launchpad.net/~data-platform/+archive/ubuntu/mysql-shell))
* Percona XtraBackup (based on Canonical  [backport](https://launchpad.net/~data-platform/+archive/ubuntu/xtrabackup))
* Prometheus MySQLd Exporter (based on Canonical [backport](https://launchpad.net/~data-platform/+archive/ubuntu/mysqld-exporter))
* Prometheus MySQL Router Exporter (based on Canonical [backport](https://launchpad.net/~data-platform/+archive/ubuntu/mysqlrouter-exporter))
* Prometheus Grafana dashboards and Loki alert rules are part of the charm revision and missing in SNAP.

Versions of all the components above are carefully chosen to fit functionality of each other.

The Charmed MySQL unit consisting of a several services which are enabled/activated accordingly to the setup: 

```
> snap services charmed-mysql
Service                              Startup   Current   Notes
charmed-mysql.mysqld                 enabled   active    -
charmed-mysql.mysqld-exporter        disabled  inactive  -
charmed-mysql.mysqlrouter-service    disabled  inactive  -
charmed-mysql.mysqlrouterd-exporter  disabled  inactive  -
```

The `mysqld` snap service is a main MySQL instance which is normally up and running right after the charm deployment.

The `mysql-router` snap service used in [Charmed MySQL Router](https://charmhub.io/mysql-router?channel=dpe/edge) only and should be stopped on [Charmed MySQL](https://charmhub.io/mysql) deployments.

All `exporter` services are activated after the relation with [COS Monitoring](/how-to/monitoring-cos/enable-monitoring) only.

> **Note:** it is possible to star/stop/restart snap services manually but it is NOT recommended to avoid a split brain with a charm state machine! Do it with a caution!!!

> **Important:** all snap resources must be executed under the special user `snapd_daemon` only!

The snap "charmed-mysql" also ships list of tools used by charm:
* `charmed-mysql.mysql` (alias `mysql`) - mysql client to connect `mysqld`.
* `charmed-mysql.mysqlsh` - new [mysql-shell](https://dev.mysql.com/doc/mysql-shell/8.0/en/) client to configure MySQL cluster.
* `charmed-mysql.xbcloud` - a tool to download and upload full or part of xbstream archive from/to the cloud.
* `charmed-mysql.xbstream` - a tool to support simultaneous compression and streaming.
* `charmed-mysql.xtrabackup` - a tool to backup/restore MySQL DB.

The `mysql` and `mysqlsh` are well known and popular tools to manage MySQL.
The `xtrabackup (xbcloud+xbstream)` used for [MySQL Backups](/how-to/back-up-and-restore/create-a-backup) only to store backups on S3 compatible storage.

## Integrations

### MySQL Router

[MySQL Router](https://dev.mysql.com/doc/mysql-router/8.0/en/) is part of MySQL InnoDB Cluster, and is lightweight middle-ware that provides transparent routing between your application and back-end MySQL Servers. The "[Charmed MySQL Router](https://charmhub.io/mysql-router)" is an independent charm "Charmed MySQL" can be related with.

### TLS Certificates Operator

[TLS Certificates](https://charmhub.io/tls-certificates-operator) charm responsible for distributing certificates through relationship. Certificates are provided by the operator through Juju configs. For the playground deployments, the [self-signed operator](https://charmhub.io/self-signed-certificates) is available as well.

### S3 Integrator

[S3 Integrator](https://charmhub.io/s3-integrator) is an integrator charm for providing S3 credentials to Charmed MySQL which seek to access shared S3 data. Store the credentials centrally in the integrator charm and relate consumer charms as needed.

### Data Integrator

[Data Integrator](https://charmhub.io/data-integrator) charm is a solution to request DB credentials for non-native Juju applications. Not all applications implement a data_interfaces relation but allow setting credentials via config. Also, some of the applications are run outside of juju. This integrator charm allows receiving credentials which can be passed into application config directly without implementing juju-native relation.

### MySQL Test App

The charm "[MySQL Test App](https://charmhub.io/mysql-test-app)" is a Canonical test application to validate the charm installation / functionality and perform the basic performance tests.

### Grafana

Grafana is an open-source visualization tools that allows to query, visualize, alert on, and visualize metrics from mixed datasources in configurable dashboards for observability. This charms is shipped with its own Grafana dashboard and supports integration with the [Grafana Operator](https://charmhub.io/grafana-k8s) to simplify observability. Please follow [COS Monitoring](/how-to/monitoring-cos/enable-monitoring) setup.

### Loki

Loki is an open-source fully-featured logging system. This charms is shipped with support for the [Loki Operator](https://charmhub.io/loki-k8s) to collect the generated logs. Please follow [COS Monitoring](/how-to/monitoring-cos/enable-monitoring) setup.

### Prometheus

Prometheus is an open-source systems monitoring and alerting toolkit with a dimensional data model, flexible query language, efficient time series database and modern alerting approach. This charm is shipped with a Prometheus exporters, alerts and support for integrating with the [Prometheus Operator](https://charmhub.io/prometheus-k8s) to automatically scrape the targets. Please follow [COS Monitoring](/how-to/monitoring-cos/enable-monitoring) setup.

## LLD (Low Level Design)

Please check the charm state machines displayed on [workflow diagrams](https://charmhub.io/mysql-k8s/docs/e-flowcharts). The low-level logic is mostly common for both VM and K8s charms.

<!--- TODO: Describe all possible installations? Cross-model/controller? --->

### Juju events

Accordingly to the [Juju SDK](https://juju.is/docs/sdk/event): “an event is a data structure that encapsulates part of the execution context of a charm”.

For this charm, the following events are observed:

1. [`on_install`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#install): install the snap "charmed-mysql" and perform basic preparations to bootstrap the cluster on the first leader (or join the already configured cluster). 
2. [`leader-elected`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#leader-elected): generate all the secrets to bootstrap the cluster.
3. [`leader-settings-changed`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#leader-settings-changed): Handle the leader settings changed event.
4. [`start`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#start): Init/setting up the cluster node.
5. [`config_changed`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#config-changed): usually fired in response to a configuration change using the GUI or CLI. Create and set default cluster and cluster-set names in the peer relation databag (on the leader only).
6. [`update-status`](https://documentation.ubuntu.com/juju/3.6/reference/hook/#update-status): Takes care of workload health checks.
<!--- 7. database_storage_detaching: TODO: ops? event?
8. TODO: any other events?
--->

### Charm code overview

[`src/charm.py`](https://github.com/canonical/mysql-operator/blob/main/src/charm.py) is the default entry point for a charm and has the [`MySQLCharmBase`](https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py) Python class which inherits from `CharmBase`.

`CharmBase` is the base class from which all Charms are formed, defined by [Ops](https://ops.readthedocs.io/en/latest/) (Python framework for developing charms). See more information in the [Ops documentation for `CharmBase`](https://ops.readthedocs.io/en/latest/reference/ops.html#ops.CharmBase).

The `__init__` method guarantees that the charm observes all events relevant to its operation and handles them.

The VM and K8s charm flavors shares the codebase via charm libraries in [`lib/charms/mysql/v0/`](https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/):

```
charmcraft list-lib mysql
Library name    API    Patch                                                                                                                                                                                                                          
backups         0      7                                                                                                                                                                                                                              
mysql           0      45                                                                                                                                                                                                                             
s3_helpers      0      4                                                                                                                                                                                                                              
tls             0      2                                     
```

