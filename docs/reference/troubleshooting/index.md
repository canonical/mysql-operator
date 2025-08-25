# Troubleshooting

```{warning}
At the moment, there is NO ability to [pause the operator](https://warthogs.atlassian.net/browse/DPE-2545).

Make sure your troubleshooting activity will not interfere with the operator itself!
```

This page goes over general troubleshooting concepts, like Juju statuses, logs and running services. 

## Check status

The first troubleshooting step is to run `juju status` and check the statuses and messages of all applications and units. 

See [](/reference/charm-statuses) for additional recommendations based on status.

## Check logs

Always check the Juju logs before troubleshooting further:

```shell
juju debug-log --replay --tail
```

Focus on `ERRORS` (normally there should be none):

```shell
juju debug-log --replay | grep -c ERROR
```

Consider to enable `DEBUG` log level IF you are troubleshooting unexpected charm behavior:


```shell
juju model-config 'logging-config=<root>=INFO;unit=DEBUG'
```

MySQL logs are located inside the snap:


```shell
> ls -la /var/snap/charmed-mysql/common/var/log/*

/var/snap/charmed-mysql/common/var/log/mysql:
-rw-r----- 1 snap_daemon root 8021 Sep 18 22:05 error.log

/var/snap/charmed-mysql/common/var/log/mysqlsh:
-rw------- 1 snap_daemon snap_daemon 12516 Sep 18 22:05 mysqlsh.log

/var/snap/charmed-mysql/common/var/log/mysqlrouter:
# The MySQL Router should be stopped on Charmed MySQL deployments and produce no logs.
```

See [Juju logs documentation](https://juju.is/docs/juju/log) to learn more about logging.

## Check snap services

Check the operator [architecture](/explanation/architecture) first to be familiar with the content of the snap, operator building blocks, and Juju units.

To enter a unit, use:

```shell
juju ssh mysql/0 bash
```

Make sure the snap `charmed-mysql` if installed and functional:

```shell
ubuntu@juju-6692b6-0:~$ sudo snap list charmed-mysql
Name           Version  Rev  Tracking       Publisher        Notes
charmed-mysql  8.0.34   69   latest/stable  dataplatformbot  held
```

From here you can make sure all snap (systemd) services are running.

Sample outputs:

<details><summary><code>sudo snap services</code></summary>


```shell
ubuntu@juju-6692b6-0# sudo snap services
Service                            Startup   Current   Notes
charmed-mysql.mysqld               enabled   active    -
charmed-mysql.mysqld-exporter      disabled  inactive  -
charmed-mysql.mysqlrouter-service  disabled  inactive  -
```
</details>

<details><summary><code>systemctl --failed</code></summary>
```shell
ubuntu@juju-6692b6-0:~$ systemctl --failed
...
0 loaded units listed.
```
</details>

<details><summary><code>ps auxww</code></summary>

```shell
ubuntu@juju-6692b6-0:~$ ps auxww
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root           1  0.0  0.0 167432 12588 ?        Ss   22:04   0:02 /lib/systemd/systemd --system --deserialize 26
root         107  0.0  0.0   4744  1828 ?        Ss   22:04   0:00 snapfuse /var/lib/snapd/snaps/core20_2015.snap /snap/core20/2015 -o ro,nodev,allow_other,suid
root         109  0.0  0.0   4800  1616 ?        Ss   22:04   0:00 snapfuse /var/lib/snapd/snaps/lxd_24322.snap /snap/lxd/24322 -o ro,nodev,allow_other,suid
root         110  0.0  0.0   4724  1624 ?        Ss   22:04   0:02 snapfuse /var/lib/snapd/snaps/snapd_19993.snap /snap/snapd/19993 -o ro,nodev,allow_other,suid
root         223  0.0  0.0   7284  2756 ?        Ss   22:04   0:00 /usr/sbin/cron -f -P
message+     225  0.0  0.0   8848  5276 ?        Ss   22:04   0:00 @dbus-daemon --system --address=systemd: --nofork --nopidfile --systemd-activation --syslog-only
root         229  0.0  0.0  33084 18940 ?        Ss   22:04   0:00 /usr/bin/python3 /usr/bin/networkd-dispatcher --run-startup-triggers
syslog       230  0.0  0.0 152764  5124 ?        Ssl  22:04   0:00 /usr/sbin/rsyslogd -n -iNONE
root         231  0.0  0.1 2133020 33096 ?       Ssl  22:04   0:03 /usr/lib/snapd/snapd
root         233  0.0  0.0  15504  7424 ?        Ss   22:04   0:00 /lib/systemd/systemd-logind
root         248  0.0  0.0   6216  1104 pts/0    Ss+  22:04   0:00 /sbin/agetty -o -p -- \u --noclear --keep-baud console 115200,38400,9600 vt220
root         259  0.0  0.0 110084 21948 ?        Ssl  22:04   0:00 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
root         261  0.0  0.0 235556  8576 ?        Ssl  22:04   0:00 /usr/libexec/polkitd --no-debug
root        1190  0.0  0.0 295960 20720 ?        Ssl  22:04   0:00 /usr/libexec/packagekitd
systemd+    1812  0.0  0.0  16116  6516 ?        Ss   22:04   0:00 /lib/systemd/systemd-networkd
systemd+    1817  0.0  0.0  25528 12740 ?        Ss   22:04   0:00 /lib/systemd/systemd-resolved
root        1819  0.0  0.0  39780 20080 ?        Ss   22:04   0:00 /lib/systemd/systemd-journald
root        2484  0.0  0.0  11088  5848 ?        Ss   22:04   0:00 /lib/systemd/systemd-udevd
root        2817  0.0  0.0  15420  9284 ?        Ss   22:04   0:00 sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups
root        3451  0.0  0.0   7760  3472 ?        Ss   22:04   0:00 bash /etc/systemd/system/jujud-machine-1-exec-start.sh
root        3456  0.0  0.3 895284 103224 ?       Sl   22:04   0:08 /var/lib/juju/tools/machine-1/jujud machine --data-dir /var/lib/juju --machine-id 1 --debug
root        3860  0.0  0.0   4772  1756 ?        Ss   22:04   0:01 snapfuse /var/lib/snapd/snaps/core22_864.snap /snap/core22/864 -o ro,nodev,allow_other,suid
root        4036  0.0  0.0   4988  1764 ?        Ss   22:04   0:03 snapfuse /var/lib/snapd/snaps/charmed-mysql_69.snap /snap/charmed-mysql/69 -o ro,nodev,allow_other,suid
snap_da+    4830  0.0  0.0   2888  1820 ?        Ss   22:05   0:00 /bin/sh /snap/charmed-mysql/69/usr/bin/mysqld_safe --defaults-file=/var/snap/charmed-mysql/69/etc/mysql/mysql.cnf
snap_da+    5313  0.0  7.2 29251092 2394896 ?    Sl   22:05   0:07 /snap/charmed-mysql/69/usr/sbin/mysqld --defaults-file=/var/snap/charmed-mysql/69/etc/mysql/mysql.cnf --basedir=/snap/charmed-mysql/69/usr --datadir=/var/snap/charmed-mysql/common/var/lib/mysql --plugin-dir=/snap/charmed-mysql/69/usr/lib/mysql/plugin --log-error=/var/snap/charmed-mysql/common/var/log/mysql/error.log --pid-file=/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.pid --socket=/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.sock
root        5690  0.0  0.0  34128 23904 ?        S    22:05   0:00 /usr/bin/python3 src/ip_address_observer.py /usr/bin/juju-run mysql/1 /var/lib/juju/agents/unit-mysql-1/charm
ubuntu      5975  0.0  0.0  16924  9484 ?        Ss   22:05   0:00 /lib/systemd/systemd --user
ubuntu      5976  0.0  0.0 170216  4804 ?        S    22:05   0:00 (sd-pam)
root        6131  0.0  0.0  16916 10988 ?        Ss   22:07   0:00 sshd: ubuntu [priv]
ubuntu      6177  0.0  0.0  17216  7980 ?        R    22:07   0:00 sshd: ubuntu@pts/1
ubuntu      6178  0.0  0.0   9060  5204 pts/1    Ss   22:07   0:00 bash
ubuntu      6244  0.0  0.0  10460  3312 pts/1    R+   22:08   0:00 ps auxww
ubuntu@juju-6692b6-0:~$ 
```
</details>

The list of running snap/systemd services will depend on whether the charm is integrated with [COS](/how-to/monitoring-cos/enable-monitoring) and/or has [backup](/how-to/back-up-and-restore/create-a-backup) functionality. 

The snap service `charmed-mysql.mysqld` must always be active and currently running (the Linux processes `snapd`, `mysqld_safe` and `mysqld`).

## Access MySQL

To access MySQL, request `root` credentials to use `mysql`:

```shell
> juju run mysql/leader get-password username=root
password: I6ToMBOJKEPKwQG5wwUpuCcg
username: root

> juju ssh mysql/0 bash

> > mysql -h 127.0.0.1 -u root -pI6ToMBOJKEPKwQG5wwUpuCcg mysql -e "show databases"
> +-------------------------------+
> | Database                      |
> +-------------------------------+
> | information_schema            |
> | mysql                         |
> | mysql_innodb_cluster_metadata |
> | performance_schema            |
> | sys                           |
> +-------------------------------+
> ...
```

Learn more about charm users in [](/explanation/users).

Continue troubleshooting your database/SQL related issues from here.

```{admonition} Recommendations to avoid split-brain scenarios
:class: warning

* Do NOT manage users, credentials, databases, or schema directly. 
  * This prevents a split-brain situation with the operator or related (integrated) applications.
* Do NOT restart services directly
  * This prevents a split-brain situation with the operator's internal state.
  * If you see a problem with a unit, consider [removing that unit and adding a new one](scale-replicas) to recover the cluster state.
```

[Contact us](/reference/contacts) if you cannot determinate the source of your issue, or if you'd like to help us improve this document.

## Installing extra software

**We do not recommend installing any additionally software** as it may affect the stability and produce anomalies which is hard to troubleshoot and fix.

However, if you do so, always remove installed components manually at the end of troubleshooting.

To install additional software, use the standard approach:

```shell
ubuntu@juju-6692b6-0:~$ sudo apt update && sudo apt install gdb
...
Setting up gdb (12.1-0ubuntu1~22.04) ...
ubuntu@juju-6692b6-0:~$
```

```{toctree}
:titlesonly:
:maxdepth: 2

SoS report <sos-report>
Recovering from quorum loss <recover-from-quorum-loss>
```
