# Scale your Charmed MySQL

This is part of the [Charmed MySQL Tutorial](/t/charmed-mysql-tutorial-overview/9922?channel=8.0/edge). Please refer to this page for more information and the overview of the content.

## Adding and Removing units

Charmed MySQL operator uses [MySQL InnoDB Cluster](https://dev.mysql.com/doc/refman/8.0/en/mysql-innodb-cluster-introduction.html) for scaling. Being built on MySQL [Group Replication](https://dev.mysql.com/doc/refman/8.0/en/group-replication.html), provides features such as automatic membership management, fault tolerance, automatic failover, and so on. An InnoDB Cluster usually runs in a single-primary mode, with one primary instance (read-write) and multiple secondary instances (read-only). The future versions on Charmed MySQL will take advantage of a multi-primary mode, where multiple instances are primaries. Users can even change the topology of the cluster while InnoDB Cluster is online, to ensure the highest possible availability.

> **!** *Disclaimer: this tutorial hosts replicas all on the same machine, this should not be done in a production environment. To enable high availability in a production environment, replicas should be hosted on different servers to [maintain isolation](https://canonical.com/blog/database-high-availability).*


### Add cluster members (replicas)
You can add two replicas to your deployed MySQL application with:
```shell
juju add-unit mysql -n 2
```

You can now watch the scaling process in live using: `juju status --watch 1s`. It usually takes several minutes for new cluster members to be added. You’ll know that all three nodes are in sync when `juju status` reports `Workload=active` and `Agent=idle`:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  23:33:55+01:00

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

### Remove cluster members (replicas)
Removing a unit from the application, scales the replicas down. Before we scale down the replicas, list all the units with `juju status`, here you will see three units `mysql/0`, `mysql/1`, and `mysql/2`. Each of these units hosts a MySQL replica. To remove the replica hosted on the unit `mysql/2` enter:
```shell
juju remove-unit mysql/2
```

You’ll know that the replica was successfully removed when `juju status --watch 1s` reports:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  23:46:43+01:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      2  mysql  8.0/stable  147  no

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Primary
mysql/1   active    idle   1        10.234.188.214

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
```

### Scaling limitations
**Note**: the maximum number of Charmed MySQL K8s units in a single Juju application is 9. It is a limitation of MySQL Group replication, read more about all limitations [here](https://dev.mysql.com/doc/refman/8.0/en/group-replication-limitations.html).