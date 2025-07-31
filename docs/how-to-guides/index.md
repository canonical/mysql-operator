
# How-To-Guides

# How-to guides

Key processes and common tasks for managing and using Charmed MySQL on machines.

## Deployment and setup

Guidance for different cloud services:
* [Sunbeam]
* [LXD]
* [MAAS]
* [AWS EC2]
* [GCE]
* [Azure]
* [Multi-AZ]

Specific deployment scenarios and architectures:

* [Terraform]
* [Air-gapped]

## Usage and maintenance
* [Integrate with another application]
* [External network access]
* [Scale replicas]
* [Enable TLS]

## Back up and restore
* [Configure S3 AWS]
* [Configure S3 RadosGW]
* [Create a backup]
* [Restore a backup]
* [Migrate a cluster]

## Monitoring (COS)
* [Enable monitoring]
* [Enable alert rules]
* [Enable tracing]

## Upgrades
See the [Upgrades landing page] for more details.
* [Upgrade Juju]
* [Perform a minor upgrade]
* [Perform a minor rollback]

## Cross-regional (cluster-cluster) async replication
* [Deploy]
* [Clients]
* [Switchover / Failover]
* [Recovery]
* [Removal]

## Development
* [Integrate with your charm]
* [Migrate data via mysqldump]
* [Migrate data via mydumper]
* [Migrate data via backup/restore]
* [Troubleshooting]


<!--Links-->

[Sunbeam]: /how-to-guides/deploy/sunbeam
[LXD]: /how-to-guides/deploy/lxd
[MAAS]: /how-to-guides/deploy/maas
[AWS EC2]: /how-to-guides/deploy/aws-ec2
[GCE]: /how-to-guides/deploy/gce
[Azure]: /how-to-guides/deploy/azure
[Multi-AZ]: /how-to-guides/deploy/multi-az
[Terraform]: /how-to-guides/deploy/terraform
[Air-gapped]: /how-to-guides/deploy/air-gapped

[Integrate with another application]: /how-to-guides/integrate-with-another-application
[External network access]: /how-to-guides/external-network-access
[Scale replicas]: /how-to-guides/scale-replicas
[Enable TLS]: /how-to-guides/enable-tls

[Configure S3 AWS]: /how-to-guides/back-up-and-restore/configure-s3-aws
[Configure S3 RadosGW]: /how-to-guides/back-up-and-restore/configure-s3-radosgw
[Create a backup]: /how-to-guides/back-up-and-restore/create-a-backup
[Restore a backup]: /how-to-guides/back-up-and-restore/restore-a-backup
[Migrate a cluster]: /how-to-guides/back-up-and-restore/migrate-a-cluster

[Enable monitoring]: /how-to-guides/monitoring-cos/enable-monitoring
[Enable alert rules]: /how-to-guides/monitoring-cos/enable-alert-rules
[Enable tracing]: /how-to-guides/monitoring-cos/enable-tracing

[Upgrades landing page]: /how-to-guides/upgrade/index
[Upgrade Juju]: /how-to-guides/upgrade/upgrade-juju
[Perform a minor upgrade]: /how-to-guides/upgrade/perform-a-minor-upgrade
[Perform a minor rollback]: /how-to-guides/upgrade/perform-a-minor-rollback

[Integrate with your charm]: /how-to-guides/development/integrate-with-your-charm
[Migrate data via mysqldump]: /how-to-guides/development/migrate-data-via-mysqldump
[Migrate data via mydumper]: /how-to-guides/development/migrate-data-via-mydumper
[Migrate data via backup/restore]: /how-to-guides/development/migrate-data-via-backup-restore
[Troubleshooting]: /how-to-guides/development/troubleshooting/index

[Deploy]: /how-to-guides/cross-regional-async-replication/deploy
[Clients]: /how-to-guides/cross-regional-async-replication/clients
[Switchover / Failover]: /how-to-guides/cross-regional-async-replication/switchover-failover
[Recovery]: /how-to-guides/cross-regional-async-replication/recovery
[Removal]: /how-to-guides/cross-regional-async-replication/removal

-------------------------


```{toctree}
:titlesonly:
:maxdepth: 2
:glob:
:hidden:

*
*/index
