# Charmed MySQL Documentation

The Charmed MySQL Operator delivers automated operations management from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/) on the [MySQL Community Edition](https://www.mysql.com/products/community/) relational database. It is an open source, end-to-end, production-ready data platform [on top of Juju](https://juju.is/).

MySQL is the world’s most popular open source database. A relational database stores data in separate tables rather than putting all the data in one big storeroom. The database structure is organized into physical files optimized for speed. The logical data model, with objects such as data tables, views, rows, and columns, offers a flexible programming environment.

This MySQL operator charm comes in two flavours to deploy and operate MySQL on [physical/virtual machines](https://github.com/canonical/mysql-operator) and [Kubernetes](https://github.com/canonical/mysql-k8s-operator). Both offer features such as replication, TLS, password rotation, and easy to use integration with applications. The Charmed MySQL Operator meets the need of deploying MySQL in a structured and consistent manner while allowing the user flexibility in configuration. It simplifies deployment, scaling, configuration and management of MySQL in production at scale in a reliable way.

[note type="positive"]
**"Charmed MySQL", "MariaDB", "OSM MariaDB", "Percona Cluster" or "Mysql Innodb Cluster"?**

This "Charmed MySQL" operator is a new "[Charmed Operator SDK](https://juju.is/docs/sdk)"-based charm to replace a "[MariaDB](https://charmhub.io/mariadb)", "[OSM MariaDB](https://charmhub.io/charmed-osm-mariadb-k8s)", "[Percona Cluster](https://charmhub.io/percona-cluster)" and "[Mysql Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)" operators [providing](/t/charmed-mysql-k8s-explanations-interfaces-endpoints/10250) all juju-interfaces of [legacy charms](https://charmhub.io/mysql/docs/e-legacy-charm).
[/note]

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](/tag/mysql)
- [Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/mysql-operator/issues/new/choose)
- [Contacts us](/t/11867) for all further questions

## In this documentation

| | |
|--|--|
|  [Tutorials](/t/charmed-mysql-tutorial-overview/9922)</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides](/t/charmed-mysql-how-to-manage-units/9904) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/mysql/actions) </br> Technical information - specifications, APIs, architecture | [Explanation](/t/charmed-mysql-k8s-explanations-interfaces-endpoints/10250) </br> Concepts - discussion and clarification of key topics  |
