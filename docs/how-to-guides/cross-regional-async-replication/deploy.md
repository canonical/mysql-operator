
# Deploy

# Deploy Async replication

The following table shows the source and target controller/model combinations that are currently supported:

|  | AWS | GCP | Azure |
|---|---|:---:|:---:|
| AWS | ![ check ] |  |  |
| GCP |  | ![ check ] |  |
| Azure |  | | ![ check ] |

## Deploy

Deploy two MySQL Clusters, named `Rome` and `Lisbon`:
```shell
juju add-model rome    # 1st cluster location: Rome
juju add-model lisbon  # 2nd cluster location: Lisbon

juju switch rome
juju deploy mysql db1 --channel=8.0/edge --config profile=testing --config cluster-name=rome --base ubuntu@22.04

juju switch lisbon
juju deploy mysql db2 --channel=8.0/edge --config profile=testing --config cluster-name=lisbon --base ubuntu@22.04
```

```{caution}
**Note**: remove profile configuration for production deployments. Check [Profiles](/reference/profiles) for documentation.
```

## Offer

Offer asynchronous replication on the Primary cluster (Rome):
```shell
juju switch rome
juju offer db1:replication-offer replication-offer
```

(Optional) Offer asynchronous replication on StandBy cluster (Lisbon), for the future:
```shell
juju switch lisbon
juju offer db2:replication-offer replication-offer
``` 

## Consume

Consume asynchronous replication on planned `StandBy` cluster (Lisbon):
```shell
juju switch lisbon
juju consume rome.replication-offer
juju integrate replication-offer db2:replication
```
Once relations are established, cluster `Rome` will get into `Blocked` state, waiting for the replication to be created.

To do so, run the action `create-replication` on rome's leader unit.

```shell
juju switch rome
juju run db1/leader create-replication
```

(Optional) Consume asynchronous replication on the current `Primary` (Rome), for the future:
```shell
juju switch rome
juju consume lisbon.replication-offer
``` 

## Status

Run the `get-cluster-status` action with the `cluster-set=True` flag: 
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
```{caution}
**Note**: The scaling is possible before and after the asynchronous replication established/created.
```

[check]: https://img.shields.io/badge/%E2%9C%93-brightgreen

-------------------------

