# How to roll back a single cluster

**Example**: MySQL 8.0.34 -> MySQL 8.0.33<br/>
(including charm revision bump: e.g Revision 43 -> Revision 42)

```{caution}
This guide covers rollbacks for single cluster MySQL deployments. 

Before rolling back a **multi-cluster** upgrade, see [](/how-to/upgrade/upgrade-multi-cluster).
```

After a `juju refresh`, if there are any version incompatibilities in charm revisions, its dependencies, or any other unexpected failure in the upgrade process, the process will be halted and enter a failure state.

Even if the underlying MySQL cluster continue to work, it’s important to roll back the charm to a previous revision so that an update can be attempted after further inspection of the failure.

```{caution}
**Warning:** Do NOT trigger `rollback` during the running `upgrade` action! It may cause an  unpredictable MySQL cluster state!
```

## Summary of the rollback steps

1. **Prepare** the Charmed MySQL application for the in-place rollback.
2. **Roll back**. Once started, all units in a cluster will be executed sequentially. The rollback will be aborted (paused) if the unit rollback has failed.
3. **Check**. Make sure the charm and cluster are in healthy state again.

## Step 1: Prepare

To execute a rollback, we use a similar procedure to the upgrade. The difference is the charm revision to upgrade to. In this guide's example, we will refresh the charm back to revision `182`.

It is necessary to re-run `pre-upgrade-check` action on the leader unit in order to enter the upgrade recovery state:

```shell
juju run mysql/leader pre-upgrade-check
```

## Step 2: Rollback

When using charm from charmhub:
```shell
juju refresh mysql --revision=182
```

When deploying from a local charm file, one must have the previous revision charm file and run the following command:
```shell
juju refresh mysql --path=./mysql_ubuntu-22.04-amd64.charm
```
> where `mysql_ubuntu-22.04-amd64.charm` is the previous revision charm file.

The first unit will be rolled out and should rejoin the cluster after settling down. After the refresh command, the juju controller revision for the application will be back in sync with the running Charmed MySQL revision.

## Step 3: Check

Future [improvements are planned](https://warthogs.atlassian.net/browse/DPE-2621) to check the state on pods/clusters on a low level. 

For now, check `juju status` to make sure the cluster [state](/reference/charm-statuses) is OK.

