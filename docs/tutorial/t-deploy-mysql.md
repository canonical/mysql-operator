# Get a Charmed MySQL up and running

This is part of the [Charmed MySQL Tutorial](/t/charmed-mysql-tutorial-overview/9922?channel=8/edge). Please refer to this page for more information and the overview of the content.

## Deploy Charmed MySQL

To deploy Charmed MySQL, all you need to do is run the following command, which will fetch the charm from [Charmhub](https://charmhub.io/mysql?channel=edge) and deploy it to your model:
```shell
juju deploy mysql --channel edge
```

Juju will now fetch Charmed MySQL and begin deploying it to the LXD cloud. This process can take several minutes depending on how provisioned (RAM, CPU, etc) your machine is. You can track the progress by running:
```shell
juju status --watch 1s
```

This command is useful for checking the status of Charmed MySQL and gathering information about the machines hosting Charmed MySQL. Some of the helpful information it displays include IP addresses, ports, state, etc. The command updates the status of Charmed MySQL every second and as the application starts you can watch the status and messages of Charmed MySQL change. Wait until the application is ready - when it is ready, `juju status` will show:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  22:52:47+01:00

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      1  mysql  edge      95  no       Unit is ready: Mode: RW

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Unit is ready: Mode: RW

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
```
To exit the screen with `juju status --watch 1s`, enter `Ctrl+c`.
If you want to further inspect juju logs, can watch for logs with `juju debug-log`.
More info on logging at [juju logs](https://juju.is/docs/olm/juju-logs).

## Access MySQL
> **!** *Disclaimer: this part of the tutorial accesses MySQL via the `root` user. **Do not** directly interface with the root user in a production environment. In a production environment always create a separate user using [Data Integrator](https://charmhub.io/data-integrator) and connect to MySQL with that user instead. Later in the section covering Relations we will cover how to access MySQL without the root user.*

The first action most users take after installing MySQL is accessing MySQL. The easiest way to do this is via the [MySQL Command-Line Client](https://dev.mysql.com/doc/refman/8.0/en/mysql.html) `mysql`. Connecting to the database requires that you know the values for `host`, `username` and `password`. To retrieve the necessary fields please run Charmed MySQL action `get-password`:
```shell
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "4"
  results:
    password: <password>
    username: root
  status: completed
  timing:
    completed: 2023-01-29 21:58:53 +0000 UTC
    enqueued: 2023-01-29 21:58:52 +0000 UTC
    started: 2023-01-29 21:58:53 +0000 UTC

```

*Note: to request a password for a different user, use an option `username`:*
```shell
juju run-action mysql/leader get-password username=myuser --wait
```

The host’s IP address can be found with `juju status` (the unit hosting the MySQL application):
```
...
Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Unit is ready: Mode: RW
...
```

To access the units hosting Charmed MySQL use:
```shell
mysql -h 10.234.188.135 -uroot -p<password>
```
*Note: if at any point you'd like to leave the unit hosting Charmed MySQL, enter* `Ctrl+d` or type `exit`*.

The another way to access MySQL server is to ssh into Juju machine:
```shell
juju ssh mysql/leader
```

Inside the Juju virtual machine the `root` user can access MySQL DB simply calling `mysql`:
```
> juju ssh mysql/leader

Welcome to Ubuntu 22.04.1 LTS (GNU/Linux 5.19.0-29-generic x86_64)
...

ubuntu@juju-ff9064-0:~$ sudo mysql -e "show databases"
+-------------------------------+
| Database                      |
+-------------------------------+
| information_schema            |
| mysql                         |
| mysql_innodb_cluster_metadata |
| performance_schema            |
| sys                           |
+-------------------------------+

ubuntu@juju-ff9064-0:~$ sudo mysql
Welcome to the MySQL monitor.  Commands end with ; or \g.
Your MySQL connection id is 56
Server version: 8.0.32-0ubuntu0.22.04.2 (Ubuntu)

Copyright (c) 2000, 2023, Oracle and/or its affiliates.

Oracle is a registered trademark of Oracle Corporation and/or its
affiliates. Other names may be trademarks of their respective
owners.

Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

mysql>
```
*Note: if at any point you'd like to leave the mysql client, enter `Ctrl+d` or type `exit`*.

You can now interact with MySQL directly using any [MySQL Queries](https://dev.mysql.com/doc/refman/8.0/en/entering-queries.html). For example entering `SELECT VERSION(), CURRENT_DATE;` should output something like:
```
mysql> SELECT VERSION(), CURRENT_DATE;
+-------------------------+--------------+
| VERSION()               | CURRENT_DATE |
+-------------------------+--------------+
| 8.0.32-0ubuntu0.22.04.2 | 2023-01-29   |
+-------------------------+--------------+
1 row in set (0.00 sec)
```

Feel free to test out any other MySQL queries. When you’re ready to leave the mysql shell you can just type `exit`. Once you've typed `exit` you will be back in the host of Charmed MySQL (`mysql/0`). Exit this host by once again typing `exit`. Now you will be in your original shell where you first started the tutorial; here you can interact with Juju and LXD.