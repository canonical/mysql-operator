# Refresh (upgrade)

This charm supports in-place upgrades to higher versions via Juju's [`refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/#details) command.

<!--TODO: clarify compatible refreshes (revision 240+?) -->

To refresh a **single cluster**, see:

* [](/how-to/refresh/refresh-single-cluster)
* [](/how-to/refresh/roll-back-single-cluster)

To refresh a **multi-cluster** deployment, see

* [](/how-to/refresh/refresh-multi-cluster)

## Juju version upgrade

Before refreshing the charm, make sure to check the [](/reference/releases) page to see if there any requirements for the new revision, such as a Juju version upgrade.

* [](/how-to/refresh/upgrade-juju)

```{toctree}
:titlesonly:
:maxdepth: 2
:hidden:

Refresh a cluster <refresh-single-cluster>
Roll back a cluster <roll-back-single-cluster>
Refresh a multi-cluster deployment <refresh-multi-cluster>
Upgrade Juju <upgrade-juju>
```
