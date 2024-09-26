# Integrating your Charmed MySQL
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` and `juju integrate` with `juju relate` for Juju 2.9.

This is part of the [Charmed MySQL Tutorial](/t/9922). Please refer to this page for more information and the overview of the content.

## Integrations (Relations for Juju 2.9)
Relations, or what Juju 3.0+ documentation [describes as an Integration](https://juju.is/docs/sdk/integration), are the easiest way to create a user for MySQL in Charmed MySQL. Relations automatically create a username, password, and database for the desired user/application. As mentioned earlier in the [Access MySQL section](#access-mysql) it is a better practice to connect to MySQL via a specific user rather than the admin user.

### Data Integrator Charm
Before relating to a charmed application, we must first deploy our charmed application. In this tutorial we will relate to the [Data Integrator Charm](https://charmhub.io/data-integrator). This is a bare-bones charm that allows for central management of database users, providing support for different kinds of data platforms (e.g. MySQL, PostgreSQL, MongoDB, Kafka, etc) with a consistent, opinionated and robust user experience. In order to deploy the Data Integrator Charm we can use the command `juju deploy` we have learned above:

```shell
juju deploy data-integrator --config database-name=test-database
```
The expected output:
```shell
Located charm "data-integrator" in charm-hub, revision 13
Deploying "data-integrator" from charm-hub charm "data-integrator", revision 3 in channel edge on jammy
```

Checking the deployment progress using `juju status` will show you the `blocked` state for newly deployed charm:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.1.6    unsupported  00:07:00+01:00

App              Version          Status   Scale  Charm            Channel     Rev  Exposed  Message
data-integrator                   blocked      1  data-integrator  stable     13    no       Please relate the data-integrator with the desired product
mysql            8.0.32-0ubun...  active       2  mysql            8.0/stable  147  no

Unit                Workload  Agent  Machine  Public address  Ports  Message
data-integrator/1*  blocked   idle   4        10.234.188.85          Please relate the data-integrator with the desired product
mysql/0*            active    idle   0        10.234.188.135         Primary
mysql/1             active    idle   1        10.234.188.214

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
4        started  10.234.188.85   juju-ff9064-4  jammy       Running
```
The `blocked` state is expected due to not-yet established relation (integration) between applications.

### Relate to MySQL
Now that the Database Integrator Charm has been set up, we can relate it to MySQL. This will automatically create a username, password, and database for the Database Integrator Charm. Relate the two applications with:
```shell
juju integrate data-integrator mysql
```
Wait for `juju status --watch 1s` to show all applications/units as `active`:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.1.6    unsupported  00:10:27+01:00

App              Version          Status  Scale  Charm            Channel     Rev  Exposed  Message
data-integrator                   active      1  data-integrator  edge       13    no
mysql            8.0.32-0ubun...  active      2  mysql            8.0/stable  147  no

Unit                Workload  Agent  Machine  Public address  Ports  Message
data-integrator/1*  active    idle   4        10.234.188.85
mysql/0*            active    idle   0        10.234.188.135         Primary
mysql/1             active    idle   1        10.234.188.214

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
4        started  10.234.188.85   juju-ff9064-4  jammy       Running
```

To retrieve information such as the username, password, and database. Enter:
```shell
juju run data-integrator/leader get-credentials
```
This should output something like:
```shell
mysql:
  database: test-database
  endpoints: 10.234.188.135:3306
  password: NZWCNOyfSElJW0u6bnQDOWAA
  read-only-endpoints: 10.234.188.214:10.234.188.85:3306
  username: relation-5
  version: 8.0.32-0ubuntu0.22.04.2
ok: "True"
```
*Note: your hostnames, usernames, and passwords will likely be different.*

### Access the related database
Use `endpoints`, `username`, `password` from above to connect newly created database `test-database` on MySQL server:
```shell
> mysql -h 10.234.188.135 -P 3306 -urelation-4 -pNZWCNOyfSElJW0u6bnQDOWAA -e "show databases"
+--------------------+
| Database           |
+--------------------+
| test-database      |
+--------------------+
```

The newly created database `test-database` is also available on all other MySQL cluster members:
```shell
> mysql -h 10.234.188.214 -P 3306 -urelation-5 -pNZWCNOyfSElJW0u6bnQDOWAA -e "show databases"
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
mysql -h 10.234.188.135 -P 3306 -urelation-5 -pNZWCNOyfSElJW0u6bnQDOWAA -e "show databases"
```

This will output an error message:
```shell
ERROR 1045 (28000): Access denied for user 'relation-5'@'_gateway.lxd' (using password: YES)
```
As this user no longer exists. This is expected as `juju remove-relation mysql data-integrator` also removes the user.
Note: data stay remain on the server at this stage!

Relate the the two applications again if you wanted to recreate the user:
```shell
juju integrate data-integrator mysql
```
Re-relating generates a new user and password:
```shell
juju run data-integrator/leader get-credentials
```
You can connect to the database with this new credentials.
From here you will see all of your data is still present in the database.