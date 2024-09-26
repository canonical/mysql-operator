# Minor Rollback

> :information_source: **Example**: MySQL 8.0.34 -> MySQL 8.0.33<br/>
(including simple charm revision bump: from revision 43 to revision 42)

> :warning: **WARNING**: do NOT trigger `rollback` during the running `upgrade` action! It may cause unpredictable MySQL Cluster state!

## Minor rollback steps

1. **Prepare** "Charmed MySQL" Juju application for the in-place rollback. See the step description below for all technical details executed by charm here.
2. **Rollback**. Once started all units in a cluster will be executed sequentially. The rollback will be aborted (paused) if the unit rollback has failed.
3. **Check**. Make sure the charm and cluster are in healthy state again.

## Manual Rollback

After a `juju refresh`, case there any version incompatibilities in charm revisions or it dependencies, or any other unexpected failure in the upgrade process, the upgrade process will be halted an enter a failure state.

Although the underlying MySQL Cluster continue to work, it’s important to rollback the charm to previous revision so an update can be later attempted after a further inspection of the failure.

To execute a rollback we take the same procedure as the upgrade, the difference being the charm revision to upgrade to. In case of this tutorial example, one would refresh the charm back to revision `182`, the steps being:

## Step 1: Prepare

It is necessary to re-run `pre-upgrade-check` action on the leader unit, to enter the upgrade recovery state:

```
juju run-action mysql/leader pre-upgrade-check --wait
```

## Step 2: Rollback

When using charm from charmhub:

```
juju refresh mysql --revision=182
```

Case deploying from local charm file, one need to have the old revision charm file and run:

```
juju refresh mysql --path=./mysql_ubuntu-22.04-amd64.charm
```

Where `mysql_ubuntu-22.04-amd64.charm` is the previous revision charm file.

The first unit will be rolled out and should rejoin the cluster after settling down. After the refresh command, the juju controller revision for the application will be back in sync with the running Charmed MySQL revision.

## Step 3: Check

The future [improvement is planned](https://warthogs.atlassian.net/browse/DPE-2621) to check the state on pod/cluster on a low level. At the moment check `juju status` to make sure the cluster [state](/t/10624) is OK.