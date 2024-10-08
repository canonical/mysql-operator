# Create and List Backups
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

Creating and listing backups requires that you:
* [Have a Charmed MySQL deployed](/t/9904)
* Access to S3 storage
* [Have configured settings for S3 storage](/t/9894)

Once Charmed MySQL is `active` and `idle` (check `juju status`), you can create your first backup with the `create-backup` command:
```shell
juju run mysql/leader create-backup
```

[note]
If you have a cluster of one unit, you can run the `create-backup` action on `mysql-k8s/leader` (which will also be the primary unit). 

Otherwise, you must run the `create-backup` action on a non-primary unit (see `juju status` or run `juju run-action mysql-k8s/leader get-cluster-status` to find the primary unit).
[/note]

You can list your available, failed, and in progress backups by running the `list-backups` command:
```shell
juju run mysql/leader list-backups
```