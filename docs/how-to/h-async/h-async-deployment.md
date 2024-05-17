# Deploy Async replication
> **WARNING**: it is an '8.0/candidate' article. Do NOT use it in production!<br/>Contact [Canonical Data Platform team](/t/11867) if you are interested in the topic.

## Deploy

Deploy two MySQL Clusters, named `Rome` and `Lisbon`:
```shell
juju add-model rome    # 1st cluster location: Rome
juju add-model lisbon  # 2nd cluster location: Lisbon

juju switch rome
juju deploy mysql-k8s db1 --channel=8.0/candidate --config profile=testing --config cluster-name=rome --base ubuntu@22.04

juju switch lisbon
juju deploy mysql-k8s db2 --channel=8.0/candidate --config profile=testing --config cluster-name=lisbon --base ubuntu@22.04
```

[note type="caution"]
**Note**: remove profile configuration for production deployments. Check [Profiles](/t/11973) for documentation.
[/note]

## Offer

Offer asynchronous replication on the Primary cluster (Rome):
```shell
juju switch rome
juju offer db1:async-primary async-primary
```

(Optional) Offer asynchronous replication on StandBy cluster (Lisbon), for the future:
```shell
juju switch lisbon
juju offer db2:async-primary async-primary
``` 

## Consume

Consume asynchronous replication on planned `StandBy` cluster (Lisbon):
```shell
juju switch lisbon
juju consume rome.async-primary
juju integrate async-primary db2:async-replica
``` 

(Optional) Consume asynchronous replication on the current `Primary` (Rome), for the future:
```shell
juju switch rome
juju consume lisbon.async-primary
``` 

## Status

Run the `get-cluster-status` action with the `cluster-set=True`flag: 
```shell
juju run -m rome db1/0 get-cluster-status cluster-set=True
```
Results:
```shell
status:
  clusters:
    lisbon:
      clusterrole: replica
      clustersetreplicationstatus: ok
      globalstatus: ok
    rome:
      clusterrole: primary
      globalstatus: ok
      primary: 10.82.12.22:3306
  domainname: cluster-set-bcba09a4d4feb2327fd6f8b0f4ac7a2c
  globalprimaryinstance: 10.82.12.22:3306
  primarycluster: rome
  status: healthy
  statustext: all clusters available.
success: "True"
```

## Scaling
The two clusters works independently, this means that it's possible to independently scaling in/out each cluster without much hassle, e.g.:
```shell
juju add-unit db1 -n 2 -m rome

juju add-unit db2 -n 2 -m lisbon
```
[note type="caution"]
**Note**: The scaling is possible before and after the asynchronous replication established/created.
[/note]