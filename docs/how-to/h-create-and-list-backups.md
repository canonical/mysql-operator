Creating and listing backups requires that you:
* [Have a Charmed MySQL deployed](https://discourse.charmhub.io/t/charmed-mysql-tutorial-managing-units/TODO)
* Access to S3 storage
* [Have configured settings for S3 storage](https://discourse.charmhub.io/t/configuring-settings-for-s3/TODO)

Once Charmed MySQL is `active` and `idle` (check `juju status`), you can create your first backup with the `create-backup` command:
```
juju run-action mysql/leader create-backup --wait
```

You can list your available, failed, and in progress backups by running the `list-backups` command:
```
juju run-action mysql/leader list-backups --wait
```