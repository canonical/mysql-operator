# Upgrade

This section contains documentation about performing upgrades (and rollbacks) on:
* [MySQL Server (workload and charm)](mysql-upgrades)
* [Juju version](#juju-upgrades)

(mysql-upgrades)=
## MySQL upgrades (refresh)

This charm supports in-place upgrades versions of MySQL via Juju's [`refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/#details) command.

<!-- warning about incompatible patch version (maybe 8.0.37) -->

See:
* [](/how-to/upgrade/upgrade-single-cluster)
* [](/how-to/upgrade/upgrade-multi-cluster-deployment)

(juju-upgrades)=
## Juju upgrades

New revisions of the charm may require that you do a major or minor Juju upgrade.

See: [](/how-to/upgrade/upgrade-juju)

```{toctree}
:titlesonly:
:maxdepth: 2
:hidden:

Upgrade Juju <upgrade-juju>
Upgrade a single cluster <upgrade-single-cluster>
Upgrade a multi-cluster setup <update-multi-cluster>
```
