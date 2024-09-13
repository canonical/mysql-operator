# How to restore backup
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

This is a How-To for performing a basic restore (restoring a locally made backup).
To restore a backup that was made from the a *different* cluster, (i.e. cluster migration via restore), please reference the [Cluster Migration via Restore How-To](/t/9906):

Restoring from a backup requires that you:
- [Scale-down to the single MySQL unit (scale it up after the backup is restored).](/t/9904)
- Access to S3 storage
- [Have configured settings for S3 storage](/t/9894)
- [Have existing backups in your S3-storage](/t/9896)

To view the available backups to restore you can enter the command `list-backups`:
```shell
juju run mysql/leader list-backups
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
juju run mysql/leader restore backup-id=YYYY-MM-DDTHH:MM:SSZ
```

Your restore will then be in progress.