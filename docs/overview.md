> This is a **IAAS/VM** operator. To deploy in Kubernetes , see [Charmed MySQL K8s](https://charmhub.io/mysql-k8s).

# Charmed MySQL documentation

Charmed MySQL is an open-source software operator that deploys and operates [MySQL Community Edition](https://www.mysql.com/products/community/) relational databases on IAAS/VM via [Juju](https://juju.is/). 

This new operator built with the [charm SDK](https://juju.is/docs/sdk) replaces [**MariaDB**](https://charmhub.io/mariadb), [**OSM MariaDB**](https://charmhub.io/charmed-osm-mariadb-k8s), [**Percona cluster**](https://charmhub.io/percona-cluster) and [**MySQL InnoDB cluster**](https://charmhub.io/mysql-innodb-cluster) operators.

Charmed MySQL includes features such as cluster-to-cluster replication, TLS encryption, password rotation, backups, and easy integration with other applications both inside and outside of Juju. It meets the need of deploying MySQL in a structured and consistent manner while allowing the user flexibility in configuration, simplifying reliable management of MySQL in production environments.

![image|690x424](upload://vpevillwv3S9C44LDFBxkGCxpGq.png)

<!--MySQL is the world’s most popular open source database. A relational database stores data in separate tables rather than putting all the data in one big storeroom. The database structure is organized into physical files optimized for speed. The logical data model, with objects such as data tables, views, rows, and columns, offers a flexible programming environment.-->

## In this documentation

| | |
|--|--|
|  [Tutorials](/t/charmed-mysql-tutorial-overview/9922)</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides](/t/charmed-mysql-how-to-manage-units/9904) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/mysql/actions) </br> Technical information - specifications, APIs, architecture | [Explanation](/t/charmed-mysql-k8s-explanations-interfaces-endpoints/10250) </br> Concepts - discussion and clarification of key topics  |

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](/tag/mysql)
- [Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/mysql-operator/issues/new/choose)
- Explore [Canonical Data Fabric solutions](https://canonical.com/data)
- [Contacts us](/t/11867) for all further questions

# Navigation

[details=Navigation]

| Level | Path | Navlink |
|---------|---------|-------------|
| 1 | tutorial | [Tutorial]() |
| 2 | t-overview | [Overview](/t/9922) |
| 2 | t-set-up | [1. Set up the environment](/t/9924) |
| 2 | t-deploy | [2. Deploy MySQL](/t/9912) |
| 2 | t-scale | [3. Scale replicas](/t/9920) |
| 2 | t-manage-passwords | [4. Manage passwords](/t/9918) |
| 2 | t-integrate | [5. Integrate applications](/t/9916) |
| 2 | t-enable-tls | [6. Enable TLS encryption](/t/9914) |
| 2 | t-clean-up | [7. Clean up the environment](/t/9910) |
| 1 | how-to | [How To]() |
| 2 | h-setup | [Deploy]() |
| 3 | h-deploy-sunbeam | [Sunbeam](/t/15986) |
| 3 | h-deploy-lxd | [LXD](/t/11870) |
| 3 | h-deploy-maas | [MAAS](/t/13900) |
| 3 | h-deploy-ec2 | [AWS EC2](/t/15718) |
| 3 | h-deploy-gce | [GCE](/t/15723) |
| 3 | h-deploy-azure | [Azure](/t/15859) |
| 3 | h-deploy-multi-az | [Multi-AZ](/t/15823) |
| 3 | h-deploy-terraform | [Terraform](/t/14925) |
| 3 | h-deploy-airgapped | [Air-gapped](/t/15747) |
| 2 | h-integrate| [Integrate with another application](/t/9902) |
| 2 | h-external-access | [External access](/t/15801) |
| 2 | h-scale | [Scale replicas](/t/9904) |
| 2 | h-enable-tls | [Enable TLS](/t/9898) |
| 2 | h-backups | [Back up and restore]() |
| 3 | h-configure-s3-aws | [Configure S3 AWS](/t/9894) |
| 3 | h-configure-s3-radosgw | [Configure S3 RadosGW](/t/10318) |
| 3 | h-create-backup | [Create a backup](/t/9896) |
| 3 | h-restore-backup | [Restore a backup](/t/9908) |
| 3 | h-migrate-cluster| [Migrate a cluster](/t/9906) |
| 2 | h-monitoring | [Monitoring (COS)]() |
| 3 | h-enable-monitoring | [Enable monitoring](/t/9900) |
| 3 | h-enable-alert-rules | [Enable alert rules](/t/15486) |
| 3 | h-enable-tracing | [Enable tracing](/t/14350) |
| 2 | h-upgrade | [Upgrade](/t/11745) |
| 3 | h-upgrade-juju | [Upgrade Juju](/t/14325) |
| 3 | h-upgrade-minor | [Perform a minor upgrade](/t/11748) |
| 3 | h-rollback-minor | [Perform a minor rollback](/t/11749) |
| 2 | h-development| [Development]() |
| 3 | h-development-integrate | [Integrate awith your charm](/t/11890) |
| 3 | h-migrate-mysqldump | [Migrate data via mysqldump](/t/11958) |
| 3 | h-migrate-mydumper | [Migrate data via mydumper](/t/11988) |
| 3 | h-migrate-backup-restore | [Migrate data via backup/restore](/t/12008) |
| 3 | h-troubleshooting | [Troubleshooting](/t/11891) |
| 2 | h-async | [Cross-regional async replication]() |
| 3 | h-async-deployment | [Deploy](/t/14169) |
| 3 | h-async-clients | [Clients](/t/14170) |
| 3 | h-async-failover | [Switchover / Failover](/t/14171) |
| 3 | h-async-recovery | [Recovery](/t/14172) |
| 3 | h-async-removal | [Removal](/t/14174) |
| 2 | h-contribute | [Contribute](/t/14654) |
| 1 | reference | [Reference]() |
| 2 | r-releases | [Releases](/t/11881) |
| 2 | r-system-requirements | [System requirements](/t/11742) |
| 2 | r-testing | [Testing](/t/11770) |
| 2 | r-profiles | [Profiles](/t/11973) |
| 2 | r-plugins-extensions | [Plugins/extensions](/t/15481) |
| 2 | r-alert-rules | [Alert rules](/t/15839) |
| 2 | r-statuses | [Statuses](/t/10624) |
| 2 | r-contacts | [Contacts](/t/11867) |
| 1 | explanation | [Explanation]() |
| 2 | e-architecture | [Architecture](/t/11756) |
| 2 | e-interfaces-endpoints | [Interfaces and endpoints](/t/10250) |
| 2 | e-users | [Users](/t/10789) |
| 2 | e-security | [Security](/t/16784) |
| 2 | e-cryptography | [Cryptography](/t/16785) |
| 2 | e-logs | [Logs](/t/11993) |
| 3 | e-audit-logs | [Audit Logs](/t/15424) |
| 2 | e-juju | [Juju](/t/11959) |
| 2 | e-legacy-charm | [Legacy charm](/t/10788) |
| 1 | search | [Search](https://canonical.com/data/docs/mysql/iaas) |

[/details]

<!--Archived
| 2 | h-development| [Development](/t/11889) |
| 3 | h-upgrade-major | [Perform a major upgrade](/t/11746) |
| 3 | h-rollback-major | [Perform a major rollback](/t/11747) |

| 3 | r-revision-312-313 | [Revision 312/313](/t/15275) |
| 3 | r-revision-240 | [Revision 240](/t/14071) |
| 3 | r-revision-196 | [Revision 196](/t/11883) |
| 3 | r-revision-151 | [Revision 151](/t/11882) |
-->