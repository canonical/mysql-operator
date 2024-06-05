# Fencing Async replication
> **WARNING**: it is an '8.0/candidate' article. Do NOT use it in production!<br/>Contact [Canonical Data Platform team](/t/11867) if you are interested in the topic.

## Pre-requisits
Make sure both `Rome` and `Lisbon` Clusters are deployed using the [Async Deployment manual](/t/14169)!

## Fencing

In case of [emergency failover](/t/14171), and there is a risk of the transaction sets differing between parts of the ClusterSet.  To avoid a split brain scenario, where more than one cluster is set as `primary`, it's important to fence all write traffic from the failed primary cluster. For doing so there's an action `fence-writes`:
```
juju run -m rome db1/leader fence-writes cluster-set-name=<my-cluster-set>
```
where `cluster-set-name` is a mandatory option to avoid human mistakes (see below).

> **Note**: The action `fence-writes` can be run against any of the Primary Cluster units.

## Unfencing

Case the old primary is reestablished and/or have all transactions reconciled, one can resume write traffic to it, by using the `unfence-writes` action, e.g.: 
```
juju run -m rome db1/leader unfence-writes cluster-set-name=<my-cluster-set>
```
where `cluster-set-name` is a mandatory option to avoid human mistakes (see below).

## ClusterSet name:
The `cluster-set-name` [can be set on deployment](https://charmhub.io/mysql/configure) and retrieved using:
```
juju run db1/0 get-cluster-status cluster-set=true

   ...
   domainname: cluster-set-bcba09a4d4feb2327fd6f8b0f4ac7a2c
   ...
```

## Extra
You can find more details about fencing in official [MySQL ClusterSet documentation](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-cluster-fencing.html).