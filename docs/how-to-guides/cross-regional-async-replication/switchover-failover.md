
# Switchover / Failover

# Switchover / Failover of Async replication

## Pre-requisites

Make sure both `Rome` and `Lisbon` Clusters are deployed using the [Async Deployment manual](/how-to-guides/cross-regional-async-replication/deploy)!

## Switchover (safe)

Assuming `Rome` is currently `Primary` and you want to promote `Lisbon` to be new primary<br/>(`Rome` will be converted to `StandBy` member):

```shell

juju run -m lisbon db2/leader promote-to-primary

```

## Failover (forced)

```{caution}

**Warning**: this is a **dangerous** operation which can cause the split-brain situation. It should be executed if Primary cluster is no longer exist (lost) ONLY! Otherwise please use safe switchover procedure above!

```

Assuming `Rome` was a `Primary` (before we lost the cluster `Rome`) and you want to promote `Lisbon` to be the new primary:

```shell

juju run -m lisbon db2/leader promote-to-primary force=True

```

> **Warning**: The `force` will cause the old primary to be invalidated.

-------------------------

