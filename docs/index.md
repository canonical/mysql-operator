## Charmed MySQL Documentation

The Charmed MySQL Operator delivers automated operations management from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/) on the [MySQL Community Edition](https://www.mysql.com/products/community/) relational database. It is an open source, end-to-end, production-ready data platform [on top of Juju](https://juju.is/).

MySQL is the world’s most popular open source database. A relational database stores data in separate tables rather than putting all the data in one big storeroom. The database structure is organized into physical files optimized for speed. The logical data model, with objects such as data tables, views, rows, and columns, offers a flexible programming environment.

This MySQL operator charm comes in two flavours to deploy and operate MySQL on [physical/virtual machines](https://github.com/canonical/mysql-operator) and [Kubernetes](https://github.com/canonical/mysql-k8s-operator). Both offer features such as replication, TLS, password rotation, and easy to use integration with applications. The Charmed MySQL Operator meets the need of deploying MySQL in a structured and consistent manner while allowing the user flexibility in configuration. It simplifies deployment, scaling, configuration and management of MySQL in production at scale in a reliable way.

[note type="positive"]
**"Charmed MySQL", "MariaDB", "OSM MariaDB", "Percona Cluster" or "Mysql Innodb Cluster"?**

"Charmed MySQL" operator is a new "[Charmed Operator SDK](https://juju.is/docs/sdk)"-based charm to replace a "[MariaDB](https://charmhub.io/mariadb)", "[OSM MariaDB](https://charmhub.io/charmed-osm-mariadb-k8s)", "[Percona Cluster](https://charmhub.io/percona-cluster)" and "[Mysql Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)" operators providing backward compatibility.
[/note]

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](/tag/mysql)
- Contribute and report bugs to [machine](https://github.com/canonical/mysql-operator) and [K8s](https://github.com/canonical/mysql-operator) operators

## In this documentation

| | |
|--|--|
|  [Tutorials -- Coming Soon]()</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides -- Coming Soon]() </br> Step-by-step guides covering key operations and common tasks |
| [Reference -- Coming Soon]() </br> Technical information - specifications, APIs, architecture | [Explanation -- Coming Soon]() </br> Concepts - discussion and clarification of key topics  |

# Navigation

| Level | Path                          | Navlink                                                                                    |
|-------|-------------------------------|--------------------------------------------------------------------------------------------|
| 1     | tutorial                      | [Tutorial]()                                                                               |
| 2     | t-overview                    | [1. Introduction](/t/charmed-mysql-tutorial-overview/9922)                                 |
| 2     | t-setup-environment           | [2. Set up the environment](/t/charmed-mysql-tutorial-setup-environment/9924)              |
| 2     | t-deploy-mysql                | [3. Deploy MySQL](/t/charmed-mysql-tutorial-deploy-mysql/9912)                             |
| 2     | t-managing-units              | [4. Manage your units](/t/charmed-mysql-tutorial-managing-units/9920)                      |
| 2     | t-manage-passwords            | [5. Manage passwords](/t/charmed-mysql-tutorial-manage-passwords/9918)                     |
| 2     | t-integrations                | [6. Relate your MySQL to other applications](/t/charmed-mysql-tutorial-integrations/9916)  |
| 2     | t-enable-security             | [7. Enable security](/t/charmed-mysql-tutorial-enable-security/9914)                       |
| 2     | t-cleanup-environment         | [8. Cleanup your environment](/t/charmed-mysql-tutorial-cleanup-environment/9910)          |
| 1     | how-to                        | [How To]()                                                                                 |
| 2     | h-manage-units                | [Manage units](/t/charmed-mysql-how-to-manage-units/9904)                                  |
| 2     | h-enable-encryption           | [Enable encryption](/t/charmed-mysql-how-to-enable-encryption/9898)                        |
| 2     | h-manage-app                  | [Manage applications](/t/charmed-mysql-how-to-manage-app/9902)                             |
| 2     | h-configure-s3                | [Configure S3](/t/charmed-mysql-how-to-configure-s3/9894)                                  |
| 2     | h-create-and-list-backups     | [Create and List Backups](/t/charmed-mysql-how-to-create-and-list-backups/9896)            |
| 2     | h-restore-backup              | [Restore a Backup](/t/charmed-mysql-how-to-restore-backup/9908)                            |
| 2     | h-migrate-cluster-via-restore | [Cluster Migration with Restore](/t/charmed-mysql-how-to-migrate-cluster-via-restore/9906) |
| 2     | h-enable-monitoring           | [Enable Monitoring](/t/charmed-mysql-how-to-enable-monitoring/9900)                        |
| 1     | reference                     | [Reference]()                                                                              |
| 2     | r-actions                     | [Actions](https://charmhub.io/mysql/actions)                                               |
| 2     | r-configurations              | [Configurations](https://charmhub.io/mysql/configure)                                      |
| 2     | r-libraries                   | [Libraries](https://charmhub.io/mysql/libraries/helpers)                                   |

# Redirects

[details=Mapping table]
| Path | Location |
| ---- | -------- |
[/details]