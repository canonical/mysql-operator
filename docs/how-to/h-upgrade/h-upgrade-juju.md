# How-to migrate on new Juju version

The juju [controller upgrade](https://juju.is/docs/juju/manage-controllers#heading--upgrade-a-controller) and [model upgrade](https://juju.is/docs/juju/manage-models#heading--upgrade-a-model) are well documented.<br/>For tech details, read the [upgrade Juju for new DB revision](/t/14325) explanation.

> **Note**: All Juju application continues running during the entire Juju upgrade process.
---

[u]Juju 3.1.5 -> 3.1.8[/u]: the [PATCH](https://semver.org/#summary) level Juju version upgrade:
```shell
> sudo snap refresh juju 

> juju upgrade-controller
# wait for upgrade controller completed

> juju upgrade-model
# wait for upgrade model completed
```
---

[u]Juju 3.1.8 -> 3.5.1[/u]: the [MAJOR/MINOR](https://semver.org/#summary) Juju version upgrade (using [migrate](https://juju.is/docs/juju/juju-migrate)):

```shell
> sudo snap refresh juju --channel 3.5/stable # choose necessary version/channel

> juju bootstrap lxd lxd_3.5.1 # --agent-version 3.5.0
...
Bootstrap complete, controller "lxd_3.5.1" is now available
...

> juju migrate lxd_3.1.8:mydatabase lxd_3.5.1
Migration started with ID "5f227519-3cdb-4538-871c-1c4589a4598a:0"
# wait for model migration completed

> juju upgrade-model -m lxd_3.5.1:mydatabase
best version:
    3.5.1
started upgrade to 3.5.1
# wait for upgrade model completed
```
---
To complete the charm upgrade itself: [refresh the charm following the manual](/t/11748).