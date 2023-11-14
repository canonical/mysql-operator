# Log rotation

## Overview

The charm stores its logs in `/var/snap/charmed-mysql/common/var/log/mysql`. It is recommended to set up a [COS integration](/t/9900) so that these log files can be streamed to Loki. This leads to better persistence and security of the logs.

```shell
root@mysql-k8s-0:/# ls -lahR /var/snap/charmed-mysql/common/var/log/mysql
/var/log/mysql:
total 28K
drwxr-xr-x 1 mysql mysql 4.0K Oct 23 20:46 .
drwxr-xr-x 1 root root 4.0K Sep 27 20:55 ..
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:46 archive_error
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:46 archive_general
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:45 archive_slowquery
-rw-r----- 1 mysql mysql 1.1K Oct 23 20:46 error.log
-rw-r----- 1 mysql mysql 1.7K Oct 23 20:46 general.log

/var/snap/charmed-mysql/common/var/log/mysql/archive_error:
total 20K
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:46 .
drwxr-xr-x 1 mysql mysql 4.0K Oct 23 20:46 ..
-rw-r----- 1 mysql mysql 8.7K Oct 23 20:44 error.log-43_2045
-rw-r----- 1 mysql mysql 2.3K Oct 23 20:45 error.log-43_2046

/var/snap/charmed-mysql/common/var/log/mysql/archive_general:
total 8.0M
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:46 .
drwxr-xr-x 1 mysql mysql 4.0K Oct 23 20:46 ..
-rw-r----- 1 mysql mysql 8.0M Oct 23 20:45 general.log-43_2045
-rw-r----- 1 mysql mysql 4.6K Oct 23 20:46 general.log-43_2046

/var/snap/charmed-mysql/common/var/log/mysql/archive_slowquery:
total 8.0K
drwxrwx--- 2 mysql mysql 4.0K Oct 23 20:45 .
drwxr-xr-x 1 mysql mysql 4.0K Oct 23 20:46 ..
```

The following is a sample of the error logs, with format `time thread [label] [err_code] [subsystem] msg`:

```shell
2023-10-24T23:28:07.048728Z mysqld_safe Number of processes running now: 0
2023-10-24T23:28:07.063027Z mysqld_safe mysqld restarted
2023-10-24T23:28:07.472084Z 0 [Warning] [MY-010101] [Server] Insecure configuration for --secure-file-priv: Location is accessible to all OS users. Consider choosing a different directory.
2023-10-24T23:28:07.472149Z 0 [System] [MY-010116] [Server] /snap/charmed-mysql/69/usr/sbin/mysqld (mysqld 8.0.34-0ubuntu0.22.04.1) starting as process 4134
2023-10-24T23:28:07.482044Z 1 [System] [MY-013576] [InnoDB] InnoDB initialization has started.
2023-10-24T23:28:11.219123Z 1 [System] [MY-013577] [InnoDB] InnoDB initialization has ended.
2023-10-24T23:28:11.486308Z 0 [Warning] [MY-010068] [Server] CA certificate ca.pem is self signed.
2023-10-24T23:28:11.487473Z 0 [System] [MY-013602] [Server] Channel mysql_main configured to support TLS. Encrypted connections are now supported for this channel.
2023-10-24T23:28:11.538807Z 0 [System] [MY-011323] [Server] X Plugin ready for connections. Bind-address: '0.0.0.0' port: 33060, socket: /var/snap/charmed-mysql/common/var/run/mysqld/mysqlx.sock
2023-10-24T23:28:11.538957Z 0 [System] [MY-010931] [Server] /snap/charmed-mysql/69/usr/sbin/mysqld: ready for connections. Version: '8.0.34-0ubuntu0.22.04.1'  socket: '/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.sock'  port: 3306  (Ubuntu).
2023-10-24T23:28:17.983851Z 12 [Warning] [MY-010604] [Repl] Neither --relay-log nor --relay-log-index were used; so replication may break when this MySQL server acts as a replica and has his hostname changed!! Please use '--relay-log=juju-9860bb-0-relay-bin' to avoid this problem.
2023-10-24T23:28:17.999093Z 12 [System] [MY-010597] [Repl] 'CHANGE REPLICATION SOURCE TO FOR CHANNEL 'mysqlsh.test' executed'. Previous state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''. New state source_host='juju-9860bb-0.lxd', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''.
2023-10-24T23:28:18.025941Z 15 [Warning] [MY-010897] [Repl] Storing MySQL user name or password information in the connection metadata repository is not secure and is therefore not recommended. Please consider using the USER and PASSWORD connection options for START REPLICA; see the 'START REPLICA Syntax' in the MySQL Manual for more information.
2023-10-24T23:28:18.046893Z 15 [ERROR] [MY-013117] [Repl] Replica I/O for channel 'mysqlsh.test': Fatal error: The replica I/O thread stops because source and replica have equal MySQL server ids; these ids must be different for replication to work (or the --replicate-same-server-id option must be used on replica but this does not always make sense; please check the manual before using it). Error_code: MY-013117
2023-10-24T23:28:18.415923Z 12 [ERROR] [MY-011685] [Repl] Plugin group_replication reported: 'The group_replication_group_name option is mandatory'
2023-10-24T23:28:18.415960Z 12 [ERROR] [MY-011660] [Repl] Plugin group_replication reported: 'Unable to start Group Replication on boot'
2023-10-24T23:28:18.442291Z 12 [System] [MY-010597] [Repl] 'CHANGE REPLICATION SOURCE TO FOR CHANNEL '__mysql_innodb_cluster_creating_cluster__' executed'. Previous state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''. New state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''.
2023-10-24T23:28:18.508247Z 12 [System] [MY-010597] [Repl] 'CHANGE REPLICATION SOURCE TO FOR CHANNEL 'group_replication_recovery' executed'. Previous state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''. New state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''.
2023-10-24T23:28:18.572495Z 12 [System] [MY-013587] [Repl] Plugin group_replication reported: 'Plugin 'group_replication' is starting.'
2023-10-24T23:28:18.622821Z 20 [System] [MY-010597] [Repl] 'CHANGE REPLICATION SOURCE TO FOR CHANNEL 'group_replication_applier' executed'. Previous state source_host='', source_port= 3306, source_log_file='', source_log_pos= 4, source_bind=''. New state source_host='<NULL>', source_port= 0, source_log_file='', source_log_pos= 4, source_bind=''.
2023-10-24T23:28:18.875230Z 0 [System] [MY-011565] [Repl] Plugin group_replication reported: 'Setting super_read_only=ON.'
2023-10-24T23:28:18.875322Z 0 [System] [MY-013471] [Repl] Plugin group_replication reported: 'Distributed recovery will transfer data using: Incremental recovery from a group donor'
2023-10-24T23:28:18.875561Z 0 [System] [MY-011565] [Repl] Plugin group_replication reported: 'Setting super_read_only=ON.'
2023-10-24T23:28:18.875596Z 0 [System] [MY-011503] [Repl] Plugin group_replication reported: 'Group membership changed to juju-9860bb-0.lxd:3306 on view 16981900988747955:1.'
2023-10-24T23:28:19.176137Z 0 [System] [MY-011490] [Repl] Plugin group_replication reported: 'This server was declared online within the replication group.'
2023-10-24T23:28:19.176342Z 0 [System] [MY-011507] [Repl] Plugin group_replication reported: 'A new primary with address juju-9860bb-0.lxd:3306 was elected. The new primary will execute all previous group transactions before allowing writes.'
2023-10-24T23:28:19.176967Z 31 [System] [MY-011565] [Repl] Plugin group_replication reported: 'Setting super_read_only=ON.'
2023-10-24T23:28:19.179244Z 28 [System] [MY-013731] [Repl] Plugin group_replication reported: 'The member action "mysql_disable_super_read_only_if_primary" for event "AFTER_PRIMARY_ELECTION" with priority "1" will be run.'
2023-10-24T23:28:19.179289Z 28 [System] [MY-011566] [Repl] Plugin group_replication reported: 'Setting super_read_only=OFF.'
2023-10-24T23:28:19.179408Z 28 [System] [MY-013731] [Repl] Plugin group_replication reported: 'The member action "mysql_start_failover_channels_if_primary" for event "AFTER_PRIMARY_ELECTION" with priority "10" will be run.'
2023-10-24T23:28:19.179600Z 31 [System] [MY-011510] [Repl] Plugin group_replication reported: 'This server is working as primary member.'
2023-10-24T23:28:19.875216Z 12 [System] [MY-014010] [Repl] Plugin group_replication reported: 'Plugin 'group_replication' has been started.'                            
```

The following is a sample of the general logs, with format `time thread_id command_type query_body`:

```shell
Time                 Id Command    Argument                                                          
2023-10-23T20:50:02.023329Z        94 Quit                                                        
2023-10-23T20:50:02.667063Z        95 Connect                                                       
2023-10-23T20:50:02.667436Z        95 Query     /* xplugin authentication */ SELECT /*+ SET_VAR(SQL_MODE = 'TRADITIONAL') */ @@require_secure_transport, `authentication_string`, `plugin`, (`account_locked
`='Y') as is_account_locked, (`password_expired`!='N') as `is_password_expired`, @@disconnect_on_expired_password as `disconnect_on_expired_password`, @@offline_mode and (`Super_priv`='N') as `is_offline_
mode_and_not_super_user`, `ssl_type`, `ssl_cipher`, `x509_issuer`, `x509_subject` FROM mysql.user WHERE 'serverconfig' = `user` AND '%' = `host`                                                            
2023-10-23T20:50:02.668277Z        95 Query     /* xplugin authentication */ SELECT /*+ SET_VAR(SQL_MODE = 'TRADITIONAL') */ @@require_secure_transport, `authentication_string`, `plugin`, (`account_locked
`='Y') as is_account_locked, (`password_expired`!='N') as `is_password_expired`, @@disconnect_on_expired_password as `disconnect_on_expired_password`, @@offline_mode and (`Super_priv`='N') as `is_offline_
mode_and_not_super_user`, `ssl_type`, `ssl_cipher`, `x509_issuer`, `x509_subject` FROM mysql.user WHERE 'serverconfig' = `user` AND '%' = `host`                                                            
2023-10-23T20:50:02.668778Z        95 Query     select @@lower_case_table_names, @@version, connection_id(), variable_value from performance_schema.session_status where variable_name = 'mysqlx_ssl_cipher'
2023-10-23T20:50:02.669991Z        95 Query     SET sql_log_bin = 0                       
2023-10-23T20:50:02.670389Z        95 Query     FLUSH SLOW LOGS                              
2023-10-23T20:50:02.670924Z        95 Quit  
```

The following is a sample of the slowquery log:

```shell
Time                 Id Command    Argument
# Time: 2023-10-23T22:22:47.564327Z
# User@Host: serverconfig[serverconfig] @ localhost [127.0.0.1]  Id:    21
# Query_time: 15.000332  Lock_time: 0.000000 Rows_sent: 0  Rows_examined: 1
SET timestamp=1698099752;
do sleep(15);
```

The charm currenly has error and general logs enabled by default, while slow query logs are disabled by default. All of these files are rotated if present into a separate dedicated archive folder under the logs directory.

We do not yet support the rotation of binary logs (binlog, relay log, undo log, redo log, etc).

## Log Rotation Configurations

For each log (error, general and slow query):

- The log file is rotated every minute (even if the log files are empty)
- The rotated log file is formatted with a date suffix of `-%V-%H%M` (-weeknumber-hourminute)
- The rotated log files are not compressed or mailed
- The rotated log files are owned by the `snap_daemon` user and group
- The rotated log files are retained for a maximux of 7 days before being deleted
- The most recent 10080 rotated log files are retained before older rotated log files are deleted

The following are logrotate config values used for log rotation:

| Option | Value |
| --- | --- |
| su | snap_daemon snap_daemon |
| createoldddir | 770 snap_daemon snap_daemon |
| hourly | true |
| maxage | 7 |
| rotate | 10080 |
| dateext | true |
| dateformat | -%V-%H%M |
| ifempty | true |
| missingok | true |
| nocompress | true |
| nomail | true |
| nosharedscripts | true |
| nocopytruncate | true |
| olddir | archive_error / archive_general / archive_slowquery |

## HLD (High Level Design)

There is a cron job on the machine where the charm exists that is triggered every minute and runs `logrotate`. The logrotate utility does *not* use `copytruncate`. Instead, the existing log file is moved into the archive directory by logrotate, and then the logrotate's postrotate script invokes `juju-run` (or `juju-exec` depending on the juju version) to dispatch a custom event. This custom event's handler flushes the MySQL log with the [FLUSH](https://dev.mysql.com/doc/refman/8.0/en/flush.html) statement that will result in a new and empty log file being created under `/var/snap/charmed-mysql/common/var/log/mysql` and the rotated file's descriptor being closed.

We use a custom event in juju to execute the FLUSH statement in order to avoid storing any credentials on the disk. The charm code has a mechanism that will retrieve credentials from the peer relation databag or juju secrets backend, if available, and keep these credentials in memory for the duration of the event handler.