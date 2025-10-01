# How to upgrade a multi-cluster deployment

A MySQL multi-cluster deployment (also known as a multi-node cluster or cluster set) can be upgraded by performing a refresh of each cluster individually.

This guide goes over the steps and important considerations before refreshing multiple MySQL clusters.

## Determine cluster order

To upgrade a multi-cluster deployment, each cluster must be refreshed one by one - starting with the standby clusters.

**The primary cluster must be the last one to get refreshed.**

When a primary cluster gets refreshed, it triggers a potentially costly re-election process. To minimise this cost, all standby clusters should be refreshed before the primary.

<!--TODO: Mention how to identify primary cluster-->

## Refresh each cluster

For each cluster, follow the instructions in [](/how-to/upgrade/upgrade-single-cluster).

**Perform a health check before proceeding to the next cluster.**

Use the [`get-cluster-status`](https://charmhub.io/mysql/actions#get-cluster-status) Juju action to check that everything is healthy after refreshing a cluster.

<!---TODO: example of running get-cluster-status (and making sure the cluster-set param is True?)
```shell
juju run <?> get-cluster-status
```
-->

## Roll back

If something goes wrong, roll back the cluster. See: [](/how-to/upgrade/roll-back-single-cluster)

<!--TODO: clarify what to do if you've already refreshed one or more clusters, another one fails, and you need to roll back everything - including the clusters that are fully upgraded -->



