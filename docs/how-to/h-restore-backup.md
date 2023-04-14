This is a How-To for performing a basic restore (restoring a locally made backup).
To restore a backup that was made from the a *different* cluster, (i.e. cluster migration via restore), please reference the [Cluster Migration via Restore How-To](/t/charmed-mysql-how-to-migrate-cluster-via-restore/9906?channel=8.0/edge):

Restoring from a backup requires that you:
- [Scale-down to the single MySQL unit (scale it up after the backup is restored).](/t/charmed-mysql-how-to-manage-units/9904?channel=8.0/edge)
- Access to S3 storage
- [Have configured settings for S3 storage](/t/charmed-mysql-how-to-configure-s3/9894?channel=8.0/edge)
- [Have existing backups in your S3-storage](/t/charmed-mysql-how-to-create-and-list-backups/9896?channel=8.0/edge)

To view the available backups to restore you can enter the command `list-backups`:
```shell
juju run-action mysql/leader list-backups --wait
```

This should show your available backups
```shell
    backups: |-
      backup-id             | backup-type  | backup-status
      ----------------------------------------------------
      YYYY-MM-DDTHH:MM:SSZ  | physical     | finished
```

To restore a backup from that list, run the `restore` command and pass the `backup-id` to restore:
 ```shell
juju run-action mysql/leader restore backup-id=YYYY-MM-DDTHH:MM:SSZ --wait
```

Your restore will then be in progress.