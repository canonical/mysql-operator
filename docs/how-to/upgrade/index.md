# Upgrade (refresh)

This charm supports in-place upgrades via Juju's [`refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/#details) command.

When refreshing a **single cluster**, see:

* [](/how-to/upgrade/upgrade-single-cluster)
* [](/how-to/upgrade/roll-back-single-cluster)

When refreshing a **multi-cluster** deployment, see

* [](/how-to/upgrade/upgrade-multi-cluster)

## Juju version

Before refreshing the charm, make sure to check the [](/reference/releases) page to see if there any requirements for the new revision, such as a Juju version upgrade.

* [](/how-to/upgrade/upgrade-juju)

```{toctree}
:titlesonly:
:maxdepth: 2
:hidden:

Upgrade a cluster <upgrade-single-cluster>
Roll back a cluster <roll-back-single-cluster>
Upgrade a multi-cluster deployment <upgrade-multi-cluster>
Upgrade Juju <upgrade-juju>
```
