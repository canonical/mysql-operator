# Minor Upgrade

> :information_source: **Example**: MySQL 8.0.33 -> MySQL 8.0.34<br/>
(including simple charm revision bump: from revision 193 to revision 196).

This is part of the [Charmed MySQL Upgrade](/t/11745). Please refer to this page for more information and the overview of the content.

We strongly recommend to **NOT** perform any other extraordinary operations on Charmed MySQL cluster, while upgrading. As an examples, these may be (but not limited to) the following:

1. Adding or removing units
2. Creating or destroying new relations
3. Changes in workload configuration
4. Upgrading other connected/related/integrated applications simultaneously

The concurrency with other operations is not supported, and it can lead the cluster into inconsistent states.

> **:warning: NOTE:** Make sure to have a [backup](/t/9896) of your data when running any type of upgrades!

> **:information_source: TIP:** It’s recommended to deploy your application in conjunction with the [Charmed MySQL Router](https://charmhub.io/mysql-router). This will ensure minimal service disruption, if any.

## Minor upgrade steps

1. **Collect** all necessary pre-upgrade information. It will be necessary for the rollback (if requested). Do NOT skip this step, it is better safe the sorry!
2. **Prepare** "Charmed MySQL" Juju application for the in-place upgrade. See the step description below for all technical details executed by charm here.
3. **Upgrade**. Once started all units in a cluster will be executed sequentially. The upgrade will be aborted (paused) if the unit upgrade has failed.
4. (optional) Consider to [**Rollback**](/t/11749) in case of disaster. Please inform and include us in your case scenario troubleshooting to trace the source of the issue and prevent it in the future. [Contact us](https://chat.charmhub.io/charmhub/channels/data-platform)!
5. Post-upgrade **check**. Make sure all units are in the proper state and the cluster is healthy.

## Step 1: Collect

> **:information_source: NOTE:** The step is only valid when deploying from charmhub. If the [local charm](https://juju.is/docs/sdk/deploy-a-charm) deployed (revision is small, e.g. 0-10), make sure the proper/current local revision of the `.charm` file is available BEFORE going further. You might need it for rollback.

The first step is to record the revision of the running application, as a safety measure for a rollback action. To accomplish this, simply run the `juju status` command and look for the deployed Charmed MySQL revision in the command output, e.g.:

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

## Step 2: Prepare

Before running the `juju refresh` command it’s necessary to run the `pre-upgrade-check` action against the leader unit:

```shell
juju run-action mysql/leader pre-upgrade-check --wait
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

## Step 3: Upgrade

Use the [`juju refresh`](https://juju.is/docs/juju/juju-refresh) command to trigger the charm upgrade process.

```shell
# example with channel selection
juju refresh mysql --channel 8.0/edge

# example with specific revision selection
juju refresh mysql --revision=183

# example with a local charm file
juju refresh mysql --path ./mysql_ubuntu-22.04-amd64.charm
```

All units are going to be refreshed (i.e. receive new charm content), and the upgrade will execute one unit at the time. The `juju status` will look like*:

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

After each unit completes the upgrade, the message `upgrade completed` is set for it, and a next unit follow, e.g.:

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

> **:information_source: Note:** It is expected to have some status changes during the process: waiting, maintenance, active. Do NOT trigger `rollback` procedure during the running `upgrade` procedure. Make sure `upgrade` has failed/stopped and cannot be fixed/continued before triggering `rollback`!

> **:information_source: Note:** Each unit should recover shortly after the upgrade, but the time can vary depending on the amount of data written to the cluster while the unit was not part of the cluster. Please be patient on the huge installations.

After a `juju refresh`, case there any version incompatibilities in charm revisions or it dependencies, or any other unexpected failure in the upgrade process, the upgrade process will be halted an enter a failure state.

## Step 4: Rollback (optional)

The step must be skipped if the upgrade went well! 

Although the underlying MySQL Cluster continue to work, it’s important to rollback the charm to previous revision so an update can be later attempted after a further inspection of the failure. Please switch to the dedicated [minor rollback](/t/11749) tutorial if necessary.

## Step 5: Check

The future [improvement is planned](https://warthogs.atlassian.net/browse/DPE-2621) to check the state on pod/cluster on a low level. At the moment check `juju status` to make sure the cluster [state](/t/10624) is OK.

<!---
**TODOs:**

* Clearly describe "failure state"!!!
* How to check progress of upgrade (is it failed or running?)?
* Hints how to fix failed upgrade? mysql-shell hints....
* Describe pre-upgrade check: free space, etc.
* Hint to add extra unit to upgrade first keeping cluster "safe".
--->