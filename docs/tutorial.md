# Charmed MySQL tutorial
The Charmed MySQL Operator delivers automated operations management from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/) on the [MySQL Community Edition](https://www.mysql.com/products/community/) relational database. It is an open source, end-to-end, production-ready data platform [on top of Juju](https://juju.is/). As a first step this tutorial shows you how to get Charmed MySQL up and running, but the tutorial does not stop there. Through this tutorial you will learn a variety of operations, everything from adding replicas to advanced operations such as enabling Transport Layer Security (TLS). In this tutorial we will walk through how to:
- Set up your environment using LXD and Juju.
- Deploy MySQL using a single command.
- Access the admin database directly.
- Add high availability with MySQL InnoDB Cluster, Group Replication.
- Request and change the admin password.
- Automatically create MySQL users via Juju relations.
- Reconfigure TLS certificate in one command.

While this tutorial intends to guide and teach you as you deploy Charmed MySQL, it will be most beneficial if you already have a familiarity with:
- Basic terminal commands.
- MySQL concepts such as replication and users.

## Minimum requirements
Before we start, make sure your machine meets the following requirements:
- Ubuntu 20.04 (Focal) or later.
- 8GB of RAM.
- 2 CPU threads.
- At least 20GB of available storage.
- Access to the internet for downloading the required snaps and charms.


## Multipass environment
[Multipass](https://multipass.run/) is a quick and easy way to launch virtual machines running Ubuntu. It uses "[cloud-init](https://cloud-init.io/)" standard to install and configure all the necessary parts automatically.

Let's install Multipass from [Snap](https://snapcraft.io/multipass) and launch a new VM using "[charm-dev](https://github.com/canonical/multipass-blueprints/blob/main/v1/charm-dev.yaml)" cloud-init config:
```shell
sudo snap install multipass && \
multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev # tune CPU/RAM/HDD accordingly to your needs 
```
*Note: all 'multipass launch' params are [described here](https://multipass.run/docs/launch-command)*.

Multipass [list of commands](https://multipass.run/docs/multipass-cli-commands) is short and self-explanatory, e.g. show all running VMs:
```shell
multipass list
```

As soon as new VM started, enter inside using:
```shell
multipass shell my-vm
```
*Note: if at any point you'd like to leave Multipass VM, enter `Ctrl+d` or type `exit`*.

All the parts have been pre-installed inside VM already, like LXD and Juju (the files '/var/log/cloud-init.log' and '/var/log/cloud-init-output.log' contain all low-level installation details). Let's bootstrap Juju to use local LXD:
```shell
juju bootstrap localhost overlord
```

The controller can work with different models; models host applications such as Charmed MySQL. Set up a specific model for Charmed MySQL named ‘tutorial’:
```shell
juju add-model tutorial
```

You can now view the model you created above by entering the command `juju status` into the command line. You should see the following:
```
Model    Controller  Cloud/Region         Version  SLA          Timestamp
tutorial overlord    localhost/localhost  2.9.42   unsupported  23:20:53+01:00

Model "admin/tutorial" is empty.
```

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

## Scale Charmed MySQL
Charmed MySQL operator uses [MySQL InnoDB Cluster](https://dev.mysql.com/doc/refman/8.0/en/mysql-innodb-cluster-introduction.html) for scaling. Being built on MySQL [Group Replication](https://dev.mysql.com/doc/refman/8.0/en/group-replication.html), provides features such as automatic membership management, fault tolerance, automatic failover, and so on. An InnoDB Cluster usually runs in a single-primary mode, with one primary instance (read-write) and multiple secondary instances (read-only). The future versions on Charmed MySQL will take advantage of a multi-primary mode, where multiple instances are primaries. Users can even change the topology of the cluster while InnoDB Cluster is online, to ensure the highest possible availability.

> **!** *Disclaimer: this tutorial hosts replicas all on the same machine, this should not be done in a production environment. To enable high availability in a production environment, replicas should be hosted on different servers to [maintain isolation](https://canonical.com/blog/database-high-availability).*


### Add cluster members (replicas)
You can add two replicas to your deployed MySQL application with:
```shell
juju add-unit mysql -n 2
```

You can now watch the scaling process in live using: `juju status --watch 1s`. It usually takes several minutes for new cluster members to be added. You’ll know that all three nodes are in sync when `juju status` reports `Workload=active` and `Agent=idle`:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  23:33:55+01:00

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      3  mysql  edge      95  no

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Unit is ready: Mode: RW
mysql/1   active    idle   1        10.234.188.214         Unit is ready: Mode: RO
mysql/2   active    idle   2        10.234.188.6           Unit is ready: Mode: RO

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
2        started  10.234.188.6    juju-ff9064-2  jammy       Running
```

### Remove cluster members (replicas)
Removing a unit from the application, scales the replicas down. Before we scale down the replicas, list all the units with `juju status`, here you will see three units `mysql/0`, `mysql/1`, and `mysql/2`. Each of these units hosts a MySQL replica. To remove the replica hosted on the unit `mysql/2` enter:
```shell
juju remove-unit mysql/2
```

You’ll know that the replica was successfully removed when `juju status --watch 1s` reports:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  23:46:43+01:00

App    Version          Status  Scale  Charm  Channel  Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      2  mysql  edge      95  no

Unit      Workload  Agent  Machine  Public address  Ports  Message
mysql/0*  active    idle   0        10.234.188.135         Unit is ready: Mode: RW
mysql/1   active    idle   1        10.234.188.214         Unit is ready: Mode: RO

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
```

## Passwords
When we accessed MySQL earlier in this tutorial, we needed to use a password manually. Passwords help to secure our database and are essential for security. Over time it is a good practice to change the password frequently. Here we will go through setting and changing the password for the admin user.

### Retrieve the root password
As previously mentioned, the root password can be retrieved by running the `get-password` action on the Charmed MySQL application:
```shell
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "6"
  results:
    password: <password>
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:48:44 +0000 UTC
    enqueued: 2023-01-29 22:48:39 +0000 UTC
    started: 2023-01-29 22:48:43 +0000 UTC
```

### Rotate the root password
You can change the root password to a new random password by entering:
```shell
juju run-action mysql/leader set-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "14"
  results: {}
  status: completed
  timing:
    completed: 2023-01-29 22:50:45 +0000 UTC
    enqueued: 2023-01-29 22:50:42 +0000 UTC
    started: 2023-01-29 22:50:44 +0000 UTC
```
Please notice the `status: completed` above which means the password has been successfully updated. To be sure, please call `get-password` once again:
```shell
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "16"
  results:
    password: <new password>
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:50:50 +0000 UTC
    enqueued: 2023-01-29 22:50:49 +0000 UTC
    started: 2023-01-29 22:50:50 +0000 UTC
```
The root password should be different from the previous password.

### Set the root password
You can change the root password to a specific password by entering:
```shell
juju run-action mysql/leader set-password password=my-password --wait && \
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "24"
  results: {}
  status: completed
  timing:
    completed: 2023-01-29 22:56:15 +0000 UTC
    enqueued: 2023-01-29 22:56:11 +0000 UTC
    started: 2023-01-29 22:56:14 +0000 UTC
unit-mysql-0:
  UnitId: mysql/0
  id: "26"
  results:
    password: my-password
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:56:16 +0000 UTC
    enqueued: 2023-01-29 22:56:15 +0000 UTC
    started: 2023-01-29 22:56:15 +0000 UTC
```
The root `password` should match whatever you passed in when you entered the command.

## Integrations (Relations for Juju 2.9)
Relations, or what Juju 3.0+ documentation [describes as an Integration](https://juju.is/docs/sdk/integration), are the easiest way to create a user for MySQL in Charmed MySQL. Relations automatically create a username, password, and database for the desired user/application. As mentioned earlier in the [Access MySQL section](#access-mysql) it is a better practice to connect to MySQL via a specific user rather than the admin user.

### Data Integrator Charm
Before relating to a charmed application, we must first deploy our charmed application. In this tutorial we will relate to the [Data Integrator Charm](https://charmhub.io/data-integrator). This is a bare-bones charm that allows for central management of database users, providing support for different kinds of data platforms (e.g. MySQL, PostgreSQL, MongoDB, Kafka, etc) with a consistent, opinionated and robust user experience. In order to deploy the Data Integrator Charm we can use the command `juju deploy` we have learned above:

```shell
juju deploy data-integrator --channel edge --config database-name=test-database
```
The expected output:
```
Located charm "data-integrator" in charm-hub, revision 3
Deploying "data-integrator" from charm-hub charm "data-integrator", revision 3 in channel edge on jammy
```

Checking the deployment progress using `juju status` will show you the `blocked` state for newly deployed charm:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  00:07:00+01:00

App              Version          Status   Scale  Charm            Channel  Rev  Exposed  Message
data-integrator                   blocked      1  data-integrator  edge       3  no       Please relate the data-integrator with the desired product
mysql            8.0.32-0ubun...  active       2  mysql            edge      95  no

Unit                Workload  Agent  Machine  Public address  Ports  Message
data-integrator/1*  blocked   idle   4        10.234.188.85          Please relate the data-integrator with the desired product
mysql/0*            active    idle   0        10.234.188.135         Unit is ready: Mode: RW
mysql/1             active    idle   1        10.234.188.214         Unit is ready: Mode: RO

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
4        started  10.234.188.85   juju-ff9064-4  jammy       Running
```
The `blocked` state is expected due to not-yet established relation (integration) between applications.

### Relate to MySQL
Now that the Database Integrator Charm has been set up, we can relate it to MySQL. This will automatically create a username, password, and database for the Database Integrator Charm. Relate the two applications with:
```shell
juju relate data-integrator mysql
```
Wait for `juju status --watch 1s` to show all applications/units as `active`:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  00:10:27+01:00

App              Version          Status  Scale  Charm            Channel  Rev  Exposed  Message
data-integrator                   active      1  data-integrator  edge       3  no
mysql            8.0.32-0ubun...  active      2  mysql            edge      95  no

Unit                Workload  Agent  Machine  Public address  Ports  Message
data-integrator/1*  active    idle   4        10.234.188.85
mysql/0*            active    idle   0        10.234.188.135         Unit is ready: Mode: RW
mysql/1             active    idle   1        10.234.188.214         Unit is ready: Mode: RO

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
4        started  10.234.188.85   juju-ff9064-4  jammy       Running
```

To retrieve information such as the username, password, and database. Enter:
```shell
juju run-action data-integrator/leader get-credentials --wait
```
This should output something like:
```yaml
unit-data-integrator-1:
  UnitId: data-integrator/1
  id: "28"
  results:
    mysql:
      endpoints: 10.234.188.135:3306
      password: FbflReIypeRhDH4UZ90pbUvi
      read-only-endpoints: 10.234.188.214:3306
      username: relation-4
      version: 8.0.32-0ubuntu0.22.04.2
    ok: "True"
  status: completed
  timing:
    completed: 2023-01-29 23:11:17 +0000 UTC
    enqueued: 2023-01-29 23:11:15 +0000 UTC
    started: 2023-01-29 23:11:16 +0000 UTC
```
*Note: your hostnames, usernames, and passwords will likely be different.*

### Access the related database
Use `endpoints`, `username`, `password` from above to connect newly created database `test-database` on MySQL server:
```shell
> mysql -h 10.234.188.135 -P 3306 -urelation-4 -pFbflReIypeRhDH4UZ90pbUvi -e "show databases"
+--------------------+
| Database           |
+--------------------+
| test-database      |
+--------------------+
```

The newly created database `test-database` is also available on all other MySQL cluster members:
```shell
> mysql -h 10.234.188.214 -P 3306 -urelation-4 -pFbflReIypeRhDH4UZ90pbUvi -e "show databases"
+--------------------+
| Database           |
+--------------------+
| test-database      |
+--------------------+
```

When you relate two applications Charmed MySQL automatically sets up a new user and database for you.
Please note the database name we specified when we first deployed the `data-integrator` charm: `--config database-name=test-database`.

### Remove the user
To remove the user, remove the relation. Removing the relation automatically removes the user that was created when the relation was created. Enter the following to remove the relation:
```shell
juju remove-relation mysql data-integrator
```

Now try again to connect to the same MySQL you just used in [Access the related database](#access-the-related-database):
```shell
mysql -h 10.234.188.135 -P 3306 -urelation-4 -pFbflReIypeRhDH4UZ90pbUvi -e "show databases"
```

This will output an error message:
```
ERROR 1045 (28000): Access denied for user 'relation-4'@'_gateway.lxd' (using password: YES)
```
As this user no longer exists. This is expected as `juju remove-relation mysql data-integrator` also removes the user.
Note: data stay remain on the server at this stage!

Relate the the two applications again if you wanted to recreate the user:
```shell
juju relate data-integrator mysql
```
Re-relating generates a new user and password:
```shell
juju run-action data-integrator/leader get-credentials --wait
```
You can connect to the database with this new credentials.
From here you will see all of your data is still present in the database.

## Transport Layer Security (TLS)
[TLS](https://en.wikipedia.org/wiki/Transport_Layer_Security) is used to encrypt data exchanged between two applications; it secures data transmitted over the network. Typically, enabling TLS within a highly available database, and between a highly available database and client/server applications, requires domain-specific knowledge and a high level of expertise. Fortunately, the domain-specific knowledge has been encoded into Charmed MySQL. This means (re-)configuring TLS on Charmed MySQL is readily available and requires minimal effort on your end.

Again, relations come in handy here as TLS is enabled via relations; i.e. by relating Charmed MySQL to the [TLS Certificates Charm](https://charmhub.io/tls-certificates-operator). The TLS Certificates Charm centralises TLS certificate management in a consistent manner and handles providing, requesting, and renewing TLS certificates.


### Configure TLS
Before enabling TLS on Charmed MySQL we must first deploy the `tls-certificates-operator` charm:
```shell
juju deploy tls-certificates-operator --channel=edge --config generate-self-signed-certificates="true" --config ca-common-name="Tutorial CA"
```

Wait until the `tls-certificates-operator` is up and active, use `juju status --watch 1s` to monitor the progress:
```
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  00:40:42+01:00

App                        Version          Status  Scale  Charm                      Channel  Rev  Exposed  Message
mysql                      8.0.32-0ubun...  active      2  mysql                      edge      95  no
tls-certificates-operator                   active      1  tls-certificates-operator  edge      20  no

Unit                          Workload  Agent  Machine  Public address  Ports  Message
mysql/0*                      active    idle   0        10.234.188.135         Unit is ready: Mode: RW
mysql/1                       active    idle   1        10.234.188.214         Unit is ready: Mode: RO
tls-certificates-operator/1*  active    idle   6        10.234.188.19

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
6        started  10.234.188.19   juju-ff9064-6  focal       Running
```
*Note: this tutorial uses [self-signed certificates](https://en.wikipedia.org/wiki/Self-signed_certificate); self-signed certificates should not be used in a production cluster.*

To enable TLS on Charmed MySQL, relate the two applications:
```shell
juju relate mysql tls-certificates-operator
```

### Add external TLS certificate
Use `openssl` to connect to the MySQL and check the TLS certificate in use:
```shell
> openssl s_client -starttls mysql -connect 10.234.188.135:3306 | grep Issuer
...
depth=1 C = US, CN = Tutorial CA
...
```
Congratulations! MySQL is now using TLS certificate generated by the external application `tls-certificates-operator`.


### Remove external TLS certificate
To remove the external TLS and return to the locally generate one, unrelate applications:
```shell
juju remove-relation mysql tls-certificates-operator
```

Check the TLS certificate in use:
```shell
> openssl s_client -starttls mysql -connect 10.234.188.135:3306 | grep Issuer
```
The output should be similar to:
```
...
Issuer: CN = MySQL_Server_8.0.32_Auto_Generated_CA_Certificate
...
```
The Charmed MySQL application returned to the certificate created locally in a moment of the MySQL server installation.

## Next Steps
In this tutorial we've successfully deployed MySQL, added/removed cluster members, added/removed users to/from the database, and even enabled and disabled TLS. You may now keep your Charmed MySQL deployment running and write to the database or remove it entirely using the steps in [Remove Charmed MySQL and Juju](#remove-charmed-mysql-and-juju). If you're looking for what to do next you can:
- Run [Charmed MySQL on Kubernetes](https://github.com/canonical/mysql-k8s-operator).
- Check out our Charmed offerings of [PostgreSQL](https://charmhub.io/postgresql?channel=edge) and [Kafka](https://charmhub.io/kafka?channel=edge).
- Read about [High Availability Best Practices](https://canonical.com/blog/database-high-availability)
- [Report](https://github.com/canonical/mysql-operator/issues) any problems you encountered.
- [Give us your feedback](https://chat.charmhub.io/charmhub/channels/data-platform).
- [Contribute to the code base](https://github.com/canonical/mysql-operator)

## Remove Multipass VM
If you're done with testing and would like to free up resources on your machine, just remove Multipass VM.
*Warning: when you remove VM as shown below you will lose all the data in MySQL and any other applications inside Multipass VM!*
```shell
multipass delete --purge my-vm
```

# License:
The Charmed MySQL Operator [is distributed](https://github.com/canonical/mysql-operator/blob/main/LICENSE) under the Apache Software License, version 2.0. It installs/operates/depends on [MySQL Community Edition](https://github.com/mysql/mysql-server), which [is licensed](https://github.com/mysql/mysql-server/blob/8.0/LICENSE) under the GPL License, version 2.

## Trademark Notice
MySQL is a trademark or registered trademark of Oracle America, Inc. Other trademarks are property of their respective owners.
