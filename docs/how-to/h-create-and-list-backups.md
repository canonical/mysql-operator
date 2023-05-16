# How to create and list backups

Creating and listing backups requires that you:
* [Have a Charmed MySQL deployed](/t/charmed-mysql-how-to-manage-units/9904?channel=8.0/edge)
* Access to S3 storage
* [Have configured settings for S3 storage](/t/charmed-mysql-how-to-configure-s3/9894?channel=8.0/edge)

Once Charmed MySQL is `active` and `idle` (check `juju status`), you can create your first backup with the `create-backup` command:
```
juju run-action mysql/leader create-backup --wait
```

You can list your available, failed, and in progress backups by running the `list-backups` command:
```
juju run-action mysql/leader list-backups --wait
```