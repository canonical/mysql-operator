# How to restore foreign backup
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

This is a How-To for restoring a backup that was made from the a *different* cluster, (i.e. cluster migration via restore). To perform a basic restore please reference the [Restore How-To](/t/9908)

Restoring a backup from a previous cluster to a current cluster requires that you:
- Have a single unit Charmed MySQL deployed and running
- Access to S3 storage
- [Have configured settings for S3 storage](/t/9894)
- Have the backups from the previous cluster in your S3-storage
- Have the passwords from your previous cluster

When you restore a backup from an old cluster, it will restore the password from the previous cluster to your current cluster. Set the password of your current cluster to the previous cluster’s password:
```shell
juju run mysql/leader set-password username=root password=<previous cluster password>
juju run mysql/leader set-password username=clusteradmin password=<previous cluster password>
juju run mysql/leader set-password username=serverconfig password=<previous cluster password>
```

To view the available backups to restore you can enter the command `list-backups`:
```shell
juju run mysql/leader list-backups
```

This shows a list of the available backups (it is up to you to identify which `backup-id` corresponds to the previous-cluster):
```shell
    backups: |-
      backup-id             | backup-type  | backup-status
      ----------------------------------------------------
      YYYY-MM-DDTHH:MM:SSZ  | physical     | finished
```

To restore your current cluster to the state of the previous cluster, run the `restore` command and pass the correct `backup-id` to the command:
 ```shell
juju run mysql/leader restore backup-id=YYYY-MM-DDTHH:MM:SSZ
```

Your restore will then be in progress, once it is complete your cluster will represent the state of the previous cluster.