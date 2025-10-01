# How to upgrade a single cluster

**Example**: MySQL 8.0.33 -> MySQL 8.0.34<br/>
(including charm revision bump: e.g. Revision 193 -> Revision 196)

```{note}
This guide covers upgrades for single cluster MySQL deployments. To upgrade a multi-cluster deployment, see [](/how-to/upgrade/multi-cluster).
```

## Important information

We strongly recommend to **NOT** perform any other extraordinary operations on a Charmed MySQL cluster while upgrading. These may be (but not limited to) the following:

1. Adding or removing units
2. Creating or destroying new relations
3. Changes in workload configuration
4. Upgrading other connected/related/integrated applications simultaneously

Concurrency with other operations is not supported, and it can lead the cluster into inconsistent states.

```{caution}
Make sure to have a backup of your data when running any type of upgrades!
See: [How to create a backup](/how-to/back-up-and-restore/create-a-backup)
```

It is recommended to deploy your application in conjunction with [Charmed MySQL Router](https://charmhub.io/mysql-router). This will ensure minimal service disruption, if any.

## Summary of the upgrade steps

1. [**Collect**](step-1-collect) all necessary pre-upgrade information. It will be necessary for the rollback (if requested). Do not skip this step!
2. [**Prepare**](step-2-prepare) the Charmed MySQL application for the in-place upgrade
3. [**Upgrade**](step-3-upgrade). Once started all units in a cluster will be executed sequentially. The upgrade will be aborted (paused) if the unit upgrade has failed.
4. Consider a [**rollback**](step-4-rollback-optional) in case of disaster. Please inform and include us in your case scenario troubleshooting to trace the source of the issue and prevent it in the future. [Contact us](/reference/contacts)!
5. [Post-upgrade **check**](step-5-check). Make sure all units are in a healthy state.

(step-1-collect)=
## Step 1: Collect

```{note}
This step is only valid when deploying from [charmhub](https://charmhub.io/). 

If a [local charm](https://juju.is/docs/sdk/deploy-a-charm) is deployed (revision is small, e.g. 0-10), make sure the proper/current local revision of the `.charm` file is available BEFORE going further. You might need it for a rollback.
```

The first step is to record the revision of the running application as a safety measure for a rollback action. To accomplish this, run the `juju status` command and look for the deployed Charmed MySQL revision in the command output, e.g:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  2.9.44   unsupported  17:58:37Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.33-0ubun...  active      3  mysql           182  no       

Unit       Workload  Agent  Machine  Public address  Ports               Message
mysql/9    active    idle   13       10.169.158.70   3306/tcp,33060/tcp  
mysql/10*  active    idle   11       10.169.158.14   3306/tcp,33060/tcp  Primary
mysql/11   active    idle   12       10.169.158.217  3306/tcp,33060/tcp  

Machine  State    Address         Inst id         Series  AZ  Message
11       started  10.169.158.14   juju-b72e25-11  jammy       Running
12       started  10.169.158.217  juju-b72e25-12  jammy       Running
13       started  10.169.158.70   juju-b72e25-13  jammy       Running
```

For this example, the current revision is `182`. Store it safely to use in case of rollback!

(step-2-prepare)=
## Step 2: Prepare

Before running the [`juju refresh`](https://juju.is/docs/juju/juju-refresh) command, it’s necessary to run the `pre-upgrade-check` action against the [leader unit](https://documentation.ubuntu.com/juju/latest/reference/unit/index.html#leader-unit):

```shell
juju run mysql/leader pre-upgrade-check
```

The output of the action should look like:

```shell
unit-mysql-10:
  ...
  results: {}
  status: completed
  ...
```

The action will configure the charm to minimize the amount of primary switchover, among other preparations for a safe upgrade process. After successful execution, the charm is ready to be upgraded.

(step-3-upgrade)=
## Step 3: Upgrade

Use the [`juju refresh`](https://juju.is/docs/juju/juju-refresh) command to trigger the charm upgrade process.

Example with channel selection

```shell
juju refresh mysql --channel 8.0/edge
```

Example with specific revision selection

```shell
juju refresh mysql --revision=183
```

Example with a local charm file

```shell
juju refresh mysql --path ./mysql_ubuntu-22.04-amd64.charm
```

All units are going to be refreshed (i.e. receive new charm content), and the upgrade will execute one unit at the time. 

`juju status` will look like similar to the output below:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  2.9.44   unsupported  18:10:30Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.33-0ubun...  active      3  mysql             7  no       

Unit       Workload     Agent      Machine  Public address  Ports               Message
mysql/9    waiting      idle       13       10.169.158.70   3306/tcp,33060/tcp  other units upgrading first...
mysql/10*  waiting      idle       11       10.169.158.14   3306/tcp,33060/tcp  other units upgrading first...
mysql/11   maintenance  executing  12       10.169.158.217  3306/tcp,33060/tcp  stopping services..

Machine  State    Address         Inst id         Series  AZ  Message
11       started  10.169.158.14   juju-b72e25-11  jammy       Running
12       started  10.169.158.217  juju-b72e25-12  jammy       Running
13       started  10.169.158.70   juju-b72e25-13  jammy       Running
```

After each unit completes the upgrade, the message `upgrade completed` is displayed, and the next unit follows.

Example `juju status` during an upgrade:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  2.9.44   unsupported  18:11:21Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.33-0ubun...  active      3  mysql             7  no       

Unit       Workload     Agent      Machine  Public address  Ports               Message
mysql/9    maintenance  executing  13       10.169.158.70   3306/tcp,33060/tcp  upgrading snap...
mysql/10*  waiting      idle       11       10.169.158.14   3306/tcp,33060/tcp  other units upgrading first...
mysql/11   maintenance  idle       12       10.169.158.217  3306/tcp,33060/tcp  upgrade completed

Machine  State    Address         Inst id         Series  AZ  Message
11       started  10.169.158.14   juju-b72e25-11  jammy       Running
12       started  10.169.158.217  juju-b72e25-12  jammy       Running
13       started  10.169.158.70   juju-b72e25-13  jammy       Running
```

**Do NOT trigger `rollback` procedure during the running `upgrade` procedure.**
It is expected to have some status changes during the process: `waiting`, `maintenance`, `active`. 

Make sure `upgrade` has failed/stopped and cannot be fixed/continued before triggering `rollback`!

**Please be patient during huge installations.**
Each unit should recover shortly after the upgrade, but time can vary depending on the amount of data written to the cluster while the unit was not part of it. 

**Incompatible charm revisions or dependencies will halt the process.**
After a `juju refresh`, if there are any version incompatibilities in charm revisions, its dependencies, or any other unexpected failure in the upgrade process, the upgrade process will be halted and enter a failure state.

(step-4-rollback-optional)=
## Step 4: Rollback (optional)

The step must be skipped if the upgrade went well! 

If there was an issue with the upgrade, even if the underlying MySQL cluster continues to work, it’s important to roll back the charm to the previous revision. That way, the update can be attempted again after a further inspection of the failure. 

> See: [How to perform a minor rollback](/how-to/upgrade/perform-a-minor-rollback) 

(step-5-check)=
## Step 5: Check

Future improvements are [planned](https://warthogs.atlassian.net/browse/DPE-2621) to check the state of a cluster on a low level. 

For now, use `juju status` to make sure the cluster [state](/reference/charm-statuses) is OK.

<!---
**TODOs:**

* Clearly describe "failure state"!!!
* How to check progress of upgrade (is it failed or running?)?
* Hints how to fix failed upgrade? mysql-shell hints....
* Describe pre-upgrade check: free space, etc.
* Hint to add extra unit to upgrade first keeping cluster "safe".
--->

