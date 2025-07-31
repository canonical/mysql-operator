---
relatedlinks: "[Charmhub](https://charmhub.io/mysql)"
---

# Charmed MySQL documentation

Charmed MySQL is an open-source software operator designed to deploy and operate object-relational databases on IAAS/VM. It packages the [MySQL](https://www.mysql.com/products/community/) database management system into a charmed operator for deployment with [Juju](https://juju.is/docs/juju).

This charmed operator replaces the legacy [**MariaDB**](https://charmhub.io/mariadb), [**OSM MariaDB**](https://charmhub.io/charmed-osm-mariadb-k8s), [**Percona cluster**](https://charmhub.io/percona-cluster) and [**MySQL InnoDB cluster**](https://charmhub.io/mysql-innodb-cluster) operators.

Charmed MySQL includes features such as cluster-to-cluster replication, TLS encryption, password rotation, backups, and easy integration with other applications both inside and outside of Juju. It meets the need of deploying MySQL in a structured and consistent manner while allowing the user flexibility in configuration, simplifying reliable management of MySQL in production environments.

```{note}
This is a **IAAS/VM** operator. To deploy on Kubernetes, see [Charmed MySQL K8s](https://canonical-charmed-mysql-k8s.readthedocs-hosted.com/).
```

[//]: # (![image|690x424]&#40;upload://vpevillwv3S9C44LDFBxkGCxpGq.png&#41;)

## In this documentation

| | |
|--|--|
|  [Tutorial](/tutorial/index)</br>  Get started - a hands-on introduction to using Charmed MySQL operator for new users </br> |  [How-to guides](/how-to-guides/scale-replicas) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/mysql/actions) </br> Technical information - specifications, APIs, architecture | [Explanation](/) </br> Concepts - discussion and clarification of key topics  |

## Project and community

Charmed MySQL is an official distribution of MySQL. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](https://discourse.charmhub.io/tag/mysql)
- [Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/mysql-operator/issues/new/choose)
- Explore [Canonical Data Fabric solutions](https://canonical.com/data)
- [Contact us](/reference/contacts) for all further questions

-------------------------

```{toctree}
:titlesonly:
:maxdepth: 2
:hidden:

Home <self>
tutorial/index
how-to/index
reference/index
explanation/index
```
