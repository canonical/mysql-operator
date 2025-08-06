# Integrate with other applications

[Integrations](https://documentation.ubuntu.com/juju/3.6/reference/relation/), known as "relations" in Juju 2.9, are the easiest way to create a user for a Charmed MySQL application. 

Integrations automatically create a username, password, and database for the desired user/application. As mentioned in the [earlier section about accessing MySQL](/tutorial/2-deploy-mysql), it is better practice to connect to MySQL via a specific user instead of the `root` user.

In this section, you will learn how to integrate your Charmed MySQL with another application (charmed or not) via the Data Integrator charm. 

## Deploy `data-integrator`

In this tutorial, we will relate to the [Data Integrator charm](https://charmhub.io/data-integrator). This is a bare-bones charm that allows for central management of database users. It automatically provides credentials and endpoints that are needed to connect with a charmed database application.

 In order to deploy the Data Integrator charm we can use the command `juju deploy` we have learned above:

To deploy `data-integrator`, run

```shell
juju deploy data-integrator --config database-name=test-database
```

Example output:
```shell
Located charm "data-integrator" in charm-hub, revision 13
Deploying "data-integrator" from charm-hub charm "data-integrator", revision 3 in channel edge on jammy
```

Running `juju status` will show you `data-integrator` in a `blocked` state. This state is expected due to not-yet established relation (integration) between applications.
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.5.2    unsupported  00:07:00+01:00

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

## Integrate with MySQL

Now that the `data-integrator` charm has been set up, we can relate it to MySQL. This will automatically create a username, password, and database for `data-integrator`.

Relate the two applications with:
```shell
juju integrate data-integrator mysql
```

Wait for `juju status --watch 1s` to show all applications/units as `active`:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.5.2    unsupported  00:10:27+01:00

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

To retrieve the username, password and database name, run the command
```shell
juju run data-integrator/leader get-credentials
```
Example output:
```yaml
mysql:
  database: test-database
  endpoints: 10.234.188.135:3306
  password: NZWCNOyfSElJW0u6bnQDOWAA
  read-only-endpoints: 10.234.188.214:10.234.188.85:3306
  username: relation-5
  version: 8.0.32-0ubuntu0.22.04.2
ok: "True"
```
> Note that your hostnames, usernames, and passwords will be different.

(access-the-integrated-database)=
## Access the integrated database

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

When you integrate two applications, Charmed MySQL automatically sets up a new user and database for you. Note the database name we specified when we first deployed the `data-integrator` charm: `--config database-name=test-database`.

## Remove the user

To remove the user, remove the integration. Removing the integration automatically removes the user that was created when the integration was created. 

To remove the integration, run the following command:

```shell
juju remove-relation mysql data-integrator
```

Try to connect to the same MySQL you just used in the previous section ([Access the integrated database](access-the-integrated-database)):

```shell
mysql -h 10.234.188.135 -P 3306 -urelation-5 -pNZWCNOyfSElJW0u6bnQDOWAA -e "show databases"
```

This will output an error message, since the user no longer exists.
```shell
ERROR 1045 (28000): Access denied for user 'relation-5'@'_gateway.lxd' (using password: YES)
```
This is expected, as `juju remove-relation mysql-k8s data-integrator` also removes the user.

> **Note**: Data remains on the server at this stage.

To create a user again, re-integrate the applications:
```shell
juju integrate data-integrator mysql
```
Re-integrating generates a new user and password. Obtain these credentials as before, with the `get-credentials` action:
```shell
juju run data-integrator/leader get-credentials
```
You can connect to the database with this new credentials. From here you will see all of your data is still present in the database.

> Next step: [6. Enable TLS encryption](/tutorial/6-enable-tls-encryption)

