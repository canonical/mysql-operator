# Refresh (upgrade)

This charm supports in-place upgrades to higher versions via Juju's [`refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/#details) command.

## Supported refreshes

```{eval-rst}
+------------+------------+----------+------------+
| From                    | To                    |
+------------+------------+----------+------------+
| Charm      | MySQL      | Charm    | MySQL      |
| revision   | Version    | revision | Version    |
+============+============+==========+============+
| 366, 367   | ``8.0.41`` |          |            |
+------------+------------+----------+------------+
| 312, 313   | ``8.0.39`` | 366, 367 | ``8.0.41`` |
+------------+------------+----------+------------+
| 240        | ``8.0.36`` | 366, 367 | ``8.0.41`` |
|            |            +----------+------------+
|            |            | 312, 313 | ``8.0.39`` |
+------------+------------+----------+------------+
| 196        | ``8.0.34`` | None     |            |
+------------+------------+----------+------------+
| 151        | ``8.0.32`` | 240      | ``8.0.36`` |
|            |            +----------+------------+
|            |            | 196      | ``8.0.34`` |
+------------+------------+----------+------------+
```

Due to an upstream issue with MySQL Server version `8.0.35`, Charmed MySQL versions below [Revision 240](https://github.com/canonical/mysql-operator/releases/tag/rev240) **cannot** be upgraded using Juju's `refresh`.

To upgrade from older versions to Revision 240 or higher, the data must be migrated manually. See: [](/how-to/development/migrate-data-via-backup-restore).

### Juju version upgrade

Before refreshing the charm, make sure to check the [](/reference/releases) page to see if there any requirements for the new revision, such as a Juju version upgrade.

* [](/how-to/refresh/upgrade-juju)

## Refresh guides

To refresh a **single cluster**, see:

* [](/how-to/refresh/refresh-single-cluster)
* [](/how-to/refresh/roll-back-single-cluster)

To refresh a **multi-cluster** deployment, see

* [](/how-to/refresh/refresh-multi-cluster)

```{toctree}
:titlesonly:
:maxdepth: 2
:hidden:

Refresh a cluster <refresh-single-cluster>
Roll back a cluster <roll-back-single-cluster>
Refresh a multi-cluster deployment <refresh-multi-cluster>
Upgrade Juju <upgrade-juju>
```

<!--Links-->

[cross]: https://img.icons8.com/?size=16&id=CKkTANal1fTY&format=png&color=D00303
[check]: https://img.icons8.com/color/20/checkmark--v1.png