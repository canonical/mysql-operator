# Charmed MySQL Documentation

[note type="positive"]
This is **[IAAS/VM](https://canonical.com/data/docs)** operator. To deploy in **[K8s](https://canonical.com/data/docs)**, use [Charmed MySQL K8s](https://charmhub.io/postgresql-k8s).
[/note]

The Charmed MySQL Operator delivers automated operations management from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/) on the [MySQL Community Edition](https://www.mysql.com/products/community/) relational database. It is an open source, end-to-end, production-ready data platform [on top of Juju](https://juju.is/).

![image|690x424](upload://vpevillwv3S9C44LDFBxkGCxpGq.png)

MySQL is the world’s most popular open source database. A relational database stores data in separate tables rather than putting all the data in one big storeroom. The database structure is organized into physical files optimized for speed. The logical data model, with objects such as data tables, views, rows, and columns, offers a flexible programming environment.

This MySQL operator charm comes in two flavours to deploy and operate MySQL on [physical/virtual machines](https://github.com/canonical/mysql-operator) and [Kubernetes](https://github.com/canonical/mysql-k8s-operator). Both offer features such as replication, TLS, password rotation, and easy to use integration with applications. The Charmed MySQL Operator meets the need of deploying MySQL in a structured and consistent manner while allowing the user flexibility in configuration. It simplifies deployment, scaling, configuration and management of MySQL in production at scale in a reliable way.

[note type="positive"]
**"Charmed MySQL", "MariaDB", "OSM MariaDB", "Percona Cluster" or "Mysql Innodb Cluster"?**

This "Charmed MySQL" operator is a new "[Charmed SDK](https://juju.is/docs/sdk)"-based charm to replace a "[MariaDB](https://charmhub.io/mariadb)", "[OSM MariaDB](https://charmhub.io/charmed-osm-mariadb-k8s)", "[Percona Cluster](https://charmhub.io/percona-cluster)" and "[Mysql Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)" operators.<br/>Read more about [legacy charms here](/t/10788).
[/note]

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](/tag/mysql)
- [Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/mysql-operator/issues/new/choose)
- Explore [Canonical Data Fabric solutions](https://canonical.com/data)
- [Contacts us](/t/11867) for all further questions

## In this documentation

| | |
|--|--|
|  [Tutorials](/t/charmed-mysql-tutorial-overview/9922)</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides](/t/charmed-mysql-how-to-manage-units/9904) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/mysql/actions) </br> Technical information - specifications, APIs, architecture | [Explanation](/t/charmed-mysql-k8s-explanations-interfaces-endpoints/10250) </br> Concepts - discussion and clarification of key topics  |

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
| 2 | h-setup | [Set up]() |
| 3 | h-deploy-lxd | [Deploy on LXD](/t/11870) |
| 3 | h-deploy-maas | [Deploy on MAAS](/t/13900) |
| 3 | h-deploy-ec2 | [Deploy on AWS EC2](/t/15718) |
| 3 | h-deploy-gce | [Deploy on GCE](/t/15723) |
| 3 | h-deploy-terraform | [Deploy via Terraform](/t/14925) |
| 3 | h-scale | [Scale replicas](/t/9904) |
| 3 | h-enable-tls | [Enable TLS encryption](/t/9898) |
| 3 | h-manage-applications | [Manage client applications](/t/9902) |
| 2 | h-backups | [Back up and restore]() |
| 3 | h-configure-s3-aws | [Configure S3 AWS](/t/9894) |
| 3 | h-configure-s3-radosgw | [Configure S3 RadosGW](/t/10318) |
| 3 | h-create-backup | [Create a backups](/t/9896) |
| 3 | h-restore-backup | [Restore a backup](/t/9908) |
| 3 | h-migrate-cluster| [Migrate a cluster](/t/9906) |
| 2 | h-monitoring | [Monitoring (COS)]() |
| 3 | h-enable-monitoring | [Enable monitoring](/t/9900) |
| 3 | h-enable-tracing | [Enable tracing](/t/14350) |
| 3 | h-enable-alert-rules | [Enable Alert Rules](/t/15486) |
| 2 | h-upgrade | [Upgrade]() |
| 3 | h-upgrade-intro | [Overview](/t/11745) |
| 3 | h-upgrade-juju | [Upgrade Juju](/t/14325) |
| 3 | h-upgrade-major | [Perform a major upgrade](/t/11746) |
| 3 | h-rollback-major | [Perform a major rollback](/t/11747) |
| 3 | h-upgrade-minor | [Perform a minor upgrade](/t/11748) |
| 3 | h-rollback-minor | [Perform a minor rollback](/t/11749) |
| 2 | h-integrate-your-charm | [Integrate with your charm]() |
| 3 | h-integrate-intro | [Intro](/t/11889) |
| 3 | h-integrate-db-with-your-charm | [Integrate a database with your charm](/t/11890) |
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
| 2 | r-releases | [Release Notes]() |
| 3 | r-all-releases | [All releases](/t/11881) |
| 3 | r-revision-274-275 | [Revision 274/275](/t/15275) |
| 3 | r-revision-240 | [Revision 240](/t/14071) |
| 3 | r-revision-196 | [Revision 196](/t/11883) |
| 3 | r-revision-151 | [Revision 151](/t/11882) |
| 2 | r-system-requirements | [System requirements](/t/11742) |
| 2 | r-testing | [Testing](/t/11770) |
| 2 | r-profiles | [Profiles](/t/11973) |
| 2 | r-plugins-extensions | [Plugins/extensions](/t/15481) |
| 2 | r-contacts | [Contacts](/t/11867) |
| 1 | explanation | [Explanation]() |
| 2 | e-architecture | [Architecture](/t/11756) |
| 2 | e-interfaces-endpoints | [Interfaces and endpoints](/t/10250) |
| 2 | e-statuses | [Statuses](/t/10624) |
| 2 | e-users | [Users](/t/10789) |
| 2 | e-logs | [Logs](/t/11993) |
| 3 | e-audit-logs | [Audit Logs](/t/15424) |
| 2 | e-juju | [Juju](/t/11959) |
| 2 | e-legacy-charm | [Legacy charm](/t/10788) |
| 1 | search | [Search](https://canonical.com/data/docs/mysql/iaas) |

[/details]