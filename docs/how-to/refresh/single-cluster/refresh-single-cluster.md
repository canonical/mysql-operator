# How to refresh a single cluster

This guide covers refresh for single cluster MySQL deployments. To refresh a multi-cluster deployment, see [](/how-to/refresh/multi-cluster/refresh-multi-cluster) first.

## Important information

**Check if your current Juju version is compatible with the new charm version**.

For information about charm versions, see [](/reference/releases).

To upgrade Juju, see [](/how-to/refresh/upgrade-juju).

**Create and test a backup of your data before running any type of refresh.** See [](/how-to/back-up-and-restore/create-a-backup).

**It is recommended to integrate your application with [Charmed MySQL Router](https://charmhub.io/mysql-router).** This will ensure minimal service disruption, if any.

## Summary of the refresh steps

1. [**Collect**](step-1-collect) all necessary pre-refresh information. It will be necessary for the rollback (if requested). Do not skip this step!
2. [**Prepare**](step-2-prepare) the Charmed MySQL application for the in-place refresh
3. [**Refresh**](step-3-refresh). Once started all units in a cluster will be executed sequentially. The refresh will be aborted (paused) if the unit refresh has failed.
4. Consider a [**rollback**](step-4-rollback-optional) in case of disaster. Please inform and include us in your case scenario troubleshooting to trace the source of the issue and prevent it in the future. [Contact us](/reference/contacts)!
5. [Post-refresh **check**](step-5-check). Make sure all units are in a healthy state.

(step-1-collect)=
## Step 1: Collect

```{note}
This step is only valid when deploying from [Charmhub](https://charmhub.io/mysql). 

If a [local charm](https://juju.is/docs/sdk/deploy-a-charm) is deployed (revision is small, e.g. 0-10), make sure the proper/current local revision of the `.charm` file is available BEFORE going further. You might need it for a rollback.
```

The first step is to record the revision of the running application as a safety measure for a rollback action. To accomplish this, run the `juju status` command and look for the deployed Charmed MySQL revision in the command output, e.g:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  3.5.2    unsupported  17:58:37Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.39-0ubun...  active      3  mysql           182  no       

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

```yaml
unit-mysql-10:
  ...
  results: {}
  status: completed
  ...
```

The action will configure the charm to minimize the amount of primary switchover, among other preparations for a safe refresh process. After successful execution, the charm is ready to be refreshed.

(step-3-refresh)=
## Step 3: Refresh

If you are refreshing multiple clusters, make sure to refresh the standby clusters first. See [](/how-to/refresh/multi-cluster/refresh-multi-cluster) for more information.

Use the [`juju refresh`](https://juju.is/docs/juju/juju-refresh) command to trigger the charm refresh process. 

Example with channel selection:

```shell
juju refresh mysql --channel 8.0/stable
```

Example with specific revision selection:

```shell
juju refresh mysql --revision=366
```

Example with a local charm file:

```shell
juju refresh mysql --path ./mysql_ubuntu-22.04-amd64.charm
```

```{admonition} During an ongoing refresh
:class: warning

**Do NOT perform any other extraordinary operations on the cluster**, such as:

* Adding or removing units
* Creating or destroying new relations
* Changes in workload configuration
* Refreshing other connected/related/integrated applications simultaneously

Concurrency with other operations is not supported, and it can lead the cluster into inconsistent states.

**Do NOT trigger a rollback**. Status changes during the process are expected (e.g. `waiting`, `maintenance`, `active`) 

Make sure the refresh has failed/stopped and cannot be continued before triggering a rollback.
```

Once the `refresh` command is executed, all units will receive new charm content. The refresh will run on one unit at a time. 

`juju status` will look like similar to the output below:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  3.5.2    unsupported  18:10:30Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.39-0ubun...  active      3  mysql             7  no       

Unit       Workload     Agent      Machine  Public address  Ports               Message
mysql/9    waiting      idle       13       10.169.158.70   3306/tcp,33060/tcp  other units upgrading first...
mysql/10*  waiting      idle       11       10.169.158.14   3306/tcp,33060/tcp  other units upgrading first...
mysql/11   maintenance  executing  12       10.169.158.217  3306/tcp,33060/tcp  stopping services..

Machine  State    Address         Inst id         Series  AZ  Message
11       started  10.169.158.14   juju-b72e25-11  jammy       Running
12       started  10.169.158.217  juju-b72e25-12  jammy       Running
13       started  10.169.158.70   juju-b72e25-13  jammy       Running
```

After each unit completes the refresh, the message `refresh completed` is displayed, and the next unit follows.

Example `juju status` during an refresh:

```shell
Model    Controller  Cloud/Region         Version  SLA          Timestamp
default  vmc         localhost/localhost  3.5.2    unsupported  18:11:21Z

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.39-0ubun...  active      3  mysql             7  no       

Unit       Workload     Agent      Machine  Public address  Ports               Message
mysql/9    maintenance  executing  13       10.169.158.70   3306/tcp,33060/tcp  upgrading snap...
mysql/10*  waiting      idle       11       10.169.158.14   3306/tcp,33060/tcp  other units upgrading first...
mysql/11   maintenance  idle       12       10.169.158.217  3306/tcp,33060/tcp  upgrade completed

Machine  State    Address         Inst id         Series  AZ  Message
11       started  10.169.158.14   juju-b72e25-11  jammy       Running
12       started  10.169.158.217  juju-b72e25-12  jammy       Running
13       started  10.169.158.70   juju-b72e25-13  jammy       Running
```

**Please be patient during huge installations.**
Each unit should recover shortly after the refresh, but time can vary depending on the amount of data written to the cluster while the unit was not part of it. 

**Incompatible charm revisions or dependencies will halt the process.**
After a `juju refresh`, if there are any version incompatibilities in charm revisions, its dependencies, or any other unexpected failure in the refresh process, the refresh will be halted and enter a failure state.

(step-4-rollback-optional)=
## Step 4: Roll back

If there was an issue with the refresh, even if the underlying MySQL cluster continues to work, it’s important to roll back the charm to the previous revision. 

The update can be attempted again after a further inspection of the failure. 

See: [](/how-to/refresh/single-cluster/roll-back-single-cluster) 

(step-5-check)=
## Step 5: Check cluster health

<!--TODO: Jira issue referenced below is no longer available. Is this referring to get-cluster-status? Should we recommend this check instead of juju status?

  Future improvements are [planned](https://warthogs.atlassian.net/browse/DPE-2621) to check the state of a cluster on a low level. 
-->

Use `juju status` to make sure the cluster [state](/reference/charm-statuses) is OK.


