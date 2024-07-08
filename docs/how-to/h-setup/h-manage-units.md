# How to deploy and manage units
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

## Basic Usage

To deploy a single unit of MySQL using its default configuration
```shell
juju deploy mysql
```

It is customary to use MySQL with replication. Hence usually more than one unit (preferably an odd number to prohibit a "split-brain" scenario) is deployed. To deploy MySQL with multiple replicas, specify the number of desired units with the `-n` option.
```shell
juju deploy mysql -n <number_of_cluster_members>
```

To retrieve primary replica one can use the action `get-primary` on any of the units running MySQL:
```shell
juju run mysql/leader get-primary
```

Similarly, the primary replica is displayed as a status message in `juju status`, however one should note that this hook gets called on regular time intervals and the primary may be outdated if the status hook has not been called recently.

Further we highly suggest configuring the status hook to run frequently. In addition to reporting the primary, secondaries, and other statuses, the status hook performs self healing in the case of a network cut. To change the frequency of the update status hook do:
```shell
juju model-config update-status-hook-interval=<time(s/m/h)>
```
Note that this hook executes a read query to MySQL. On a production level server this should be configured to occur at a frequency that doesn't overload the server with read requests. Similarly the hook should not be configured at too quick of a frequency as this can delay other hooks from running. You can read more about status hooks [here](https://juju.is/docs/sdk/update-status-event).

## Replication

To scaling-up the cluster, use `juju add-unit`:
```shell
juju add-unit mysql --num-units <amount_of_units_to_add>
```

To scaling-down the cluster, use `juju remove-unit`:
```shell
juju remove-unit mysql/<unit_id_to_remove>
```

> **:warning: Warning**: be careful with removing all units! It can destroy your data ([Juju storage provider](https://juju.is/docs/juju/storage-provider) dependent)!