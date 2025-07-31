
# Clients

# Clients for Async replication

## Pre-requisites
Make sure both `Rome` and `Lisbon` Clusters are deployed using the [Async Deployment manual](/how-to/cross-regional-async-replication/deploy)!

## Offer and consume DB endpoints
```shell
juju switch rome
juju offer db1:database db1-database

juju switch lisbon
juju offer db2:database db2-database

juju add-model app ; juju switch app
juju consume rome.db1-database
juju consume lisbon.db2-database
```

## Internal Juju app/clients
```shell
juju switch app

juju deploy mysql-test-app
juju deploy mysql-router --channel dpe/edge

juju relate mysql-test-app mysql-router
juju relate mysql-router db1-database
```

## External Juju clients
```shell
juju switch app

juju deploy data-integrator --config database-name=mydatabase
juju deploy mysql-router mysql-router-external --channel dpe/edge

juju relate data-integrator mysql-router-external
juju relate mysql-router-external db1-database

juju run data-integrator/leader get-credentials
```

