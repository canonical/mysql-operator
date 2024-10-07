> [Charmed MySQL Tutorial](/t/9922) > 3. Scale your replicas

# Scale your replicas

In this section, you will learn to scale your Charmed MySQL by adding or removing juju units.

The Charmed MySQL operator uses [MySQL InnoDB Cluster](https://dev.mysql.com/doc/refman/8.0/en/mysql-innodb-cluster-introduction.html) for scaling. It is built on MySQL [Group Replication](https://dev.mysql.com/doc/refman/8.0/en/group-replication.html), providing features such as automatic membership management, fault tolerance, and automatic failover. 

An InnoDB Cluster usually runs in a single-primary mode, with one primary instance (read-write) and multiple secondary instances (read-only). 

<!-- TODO: clarify "future" Future versions on Charmed MySQL will take advantage of a multi-primary mode, where multiple instances are primaries. Users can even change the topology of the cluster while InnoDB Cluster is online, to ensure the highest possible availability. -->

[note type="caution"]
**Disclaimer:** This tutorial hosts replicas all on the same machine. **This should not be done in a production environment.** 

To enable high availability in a production environment, replicas should be hosted on different servers to [maintain isolation](https://canonical.com/blog/database-high-availability).
[/note]

## Summary
* [Add replicas](#add-replicas)
* [Remove replicas](#remove-replicas)

---

Currently, your deployment has only one [juju unit](https://juju.is/docs/juju/unit), known in juju as the leader unit.  For each MySQL replica, a new juju unit (non-leader) is created. All units are members of the same database cluster.

## Add replicas
You can add two replicas to your deployed MySQL application with:
```shell
juju add-unit mysql -n 2
```

You can now watch the scaling process in live using: `juju status --watch 1s`. It usually takes several minutes for new cluster members to be added. 

You’ll know that all three nodes are in sync when `juju status` reports `Workload=active` and `Agent=idle`:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.1.6    unsupported  23:33:55+01:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      3  mysql  8.0/stable  147  no

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Primary
mysql/1   active    idle   1        10.234.188.214
mysql/2   active    idle   2        10.234.188.6

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
2        started  10.234.188.6    juju-ff9064-2  jammy       Running
```
[note]
The maximum number of Charmed MySQL units in a single Juju application is 9. This is a limitation of MySQL Group replication. Read more about all limitations in the [official MySQL documentation](https://dev.mysql.com/doc/refman/8.0/en/group-replication-limitations.html).
[/note]

## Remove replicas
Removing a unit from the application scales down the replicas. 

Before we scale down, list all the units with `juju status`. You will see three units: `mysql/0`, `mysql/1`, and `mysql/2`. Each of these units hosts a MySQL replica. 

To remove the replica hosted on the unit `mysql/2` enter:
```shell
juju remove-unit mysql/2
```

You’ll know that the replica was successfully removed when `juju status --watch 1s` reports:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.1.6    unsupported  23:46:43+01:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      2  mysql  8.0/stable  147  no

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Primary
mysql/1   active    idle   1        10.234.188.214

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
```
<!--TODO: What about generic scaling down (without specifying which unit)?-->

> Next step: [4. Manage passwords](/t/9918)