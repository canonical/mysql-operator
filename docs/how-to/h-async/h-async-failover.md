# Switchover / Failover of Async replication
> **WARNING**: it is an '8.0/candidate' article. Do NOT use it in production!<br/>Contact [Canonical Data Platform team](/t/11867) if you are interested in the topic.

## Pre-requisits
Make sure both `Rome` and `Lisbon` Clusters are deployed using the [Async Deployment manual](/t/14169)!

## Switchover (safe)
Assuming `Rome` is currently `Primary` and you want to promote `Lisbon` to be new primary<br/>(`Rome` will be converted to `StandBy` member):
```shell
juju run -m lisbon db2/leader promote-standby-cluster cluster-set-name=<cluster-set-119185404c15ba547eb5f0750a5c34b5>
```
where `cluster-set-name` is a mandatory option to avoid human mistakes.

The cluster-set-name [can be set on deployment](https://charmhub.io/mysql/configure) and retrieved using:
```
juju run -m rome db1/0 get-cluster-status cluster-set=true

   ...
   domainname: cluster-set-bcba09a4d4feb2327fd6f8b0f4ac7a2c
   ...
```

## Failover (forced)

[note type="caution"]
**Warning**: this is a **dangerous** operation which can cause the split-brain situation. It should be executed if Primary cluster is no longer exist (lost) ONLY! Otherwise please use safe switchover procedure above! Also consider [to fence the write traffic](/t/14173) BEFORE forcing emergency failover.
[/note]

Assuming `Rome` was a `Primary` (before we lost the cluster `Rome`) and you want to promote `Lisbon` to be the new primary:
```shell
juju run -m lisbon db2/leader promote-standby-cluster cluster-set-name=<cluster-set-bcba09a4d4feb2327fd6f8b0f4ac7a2c> force=True
```
It's required to provide the `cluster-set-name` option as a foolproof method.

> **Warning**: The `force` will cause the old primary to be invalidated, make sure you have [fenced writes](/t/14173) there (fencing will reject all writes to the ClusterSet during the emergency failover)!