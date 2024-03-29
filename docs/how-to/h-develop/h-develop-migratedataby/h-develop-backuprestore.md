# DB data migration using ‘backup/restore’

> :information_source: **Tip**: use ['mysqldump' manual](/t/11958) to migrate [legacy charms](/t/10788) data.

This Charmed MySQL operator is able to restore [it's own backups](/t/9908) stored on [S3-compatible storage](/t/9894). The same restore approach is applicable to restore [foreign backups](/t/9906) made by different Charmed MySQL installation or even another MySQL charms. The backup have to be created manually using Percona XtraBackup!

> :warning: Canonical Data team describes here the general approach and does NOT support nor guaranties the restoration results. Always test migration in LAB before performing it in Production!

Before the data migration check all [limitations of the modern Charmed MySQL](/t/11742#mysql-gr-limits) charm!
Please check [your application compatibility](/t/10788) with Charmed MySQL before migrating production data from legacy charm!

The approach:

* retrieve root/admin level credentials from legacy charm. See examples [here](/t/11958).
* install [Percona XtraBackup for MySQL](https://www.percona.com/software/mysql-database/percona-xtrabackup) inside the old charm OR remotely. Ensure version is compatible with xtrabackup in `Charmed MySQL` revision you are going to deploy! See [examples](https://docs.percona.com/percona-xtrabackup/8.0/installation.html). BTW, you can use `charmed-mysql` [SNAP](https://snapcraft.io/charmed-mysql)/[ROCK](https://github.com/canonical/charmed-mysql-rock) directly (more details [here](/t/11756#hld)).
* configure storage for database backup (local or remote, S3-based is recommended).
* create a first full logical backup during the off-peak, [example of backup command](https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py#L2160-L2185).
* [restore the foreign backup](/t/9906) to Charmed MySQL Lab installation.
* perform all the necessary tests to make sure your application accepted new DB.
* schedule and perform the final production migration re-using the last steps above.

Do you have questions? [Contact us](https://chat.charmhub.io/charmhub/channels/data-platform) if you are interested in such a data migration!