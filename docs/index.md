

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
|  [Tutorials](/tutorial/index)</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides](/how-to/scale-replicas) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/mysql/actions) </br> Technical information - specifications, APIs, architecture | [Explanation](/) </br> Concepts - discussion and clarification of key topics  |

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](/tag/mysql)
- [Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/mysql-operator/issues/new/choose)
- Explore [Canonical Data Fabric solutions](https://canonical.com/data)
- [Contacts us](/reference/contacts) for all further questions

```{toctree}
:titlesonly:
:maxdepth: 2
:glob:
:hidden:

Home <self>
tutorial/index
how-to/index
reference/index
explanation/index
```
