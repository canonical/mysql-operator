# Removal of Async replication
> **WARNING**: it is an '8.0/candidate' article. Do NOT use it in production!<br/>Contact [Canonical Data Platform team](/t/11867) if you are interested in the topic.

## Pre-requisits

Make sure both `Rome` and `Lisbon` Clusters are deployed using the [Async Deployment manual](/t/14169)!

## Detach Cluster from ClusterSet

> **Note**: It is important to [switchover](/t/14171) the `Primary` Cluster before detaching it from ClusterSet!

Assuming the `Lisbon` is a current `Primary` and we want to detach `Rome` (for removal or reuse):

```shell

juju remove-relation async-primary db2:async-replica

```

The command above will move cluster `Rome` into the detached state `blocked` keeping all the data in place.

All units in `Rome` will be in a standalone (non-clusterized) read-only state.

From this points, there are three options, as described in the following sections.

## Rejoin detached cluster into previous ClusterSet

At this stage, the detached/blocked cluster `Rome` can re-join the previous ClusterSet by restoring async integration/relation:

```shell

juju switch rome

juju integrate async-primary db1:async-replica

```

## Removing detached cluster

Remove no-longer necessary Cluster `Rome` (and destroy storage if Rome data is no longer necessary):

```shell

juju remove-application db1 # --destroy-storage

```

## New ClusterSet from detached Cluster

Convert `Rome` to the new Cluster/ClusterSet keeping the current data in use:

```shell

juju run -m rome db1/leader recreate-cluster

```