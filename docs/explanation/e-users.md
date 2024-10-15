# Charm Users explanations

There are two types of users in MySQL:
* Internal users (used by charm operator)
* Relation/integration users (used by related applications)
  * Extra user roles (if default permissions are not enough)

<a name="internal-users"></a>
## Internal users explanations:

The operator uses the following internal DB users:

* `root` - the [initial/default](https://charmhub.io/mysql/docs/t-manage-passwords) MySQL user. Used for very initial bootstrap and restricted to local access.
* `clusteradmin` - the user to manage replication in the MySQL InnoDB ClusterSet.
* `serverconfig` - the user that operates MySQL instances.
* `monitoring` - the user for [COS integration](https://charmhub.io/mysql/docs/h-enable-monitoring).
* `backups` - the user to [perform/list/restore backups](https://charmhub.io/mysql/docs/h-create-and-list-backups).
* `mysql_innodb_cluster_#######` - the [internal recovery users](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-cluster-user-accounts.html#mysql-innodb-cluster-users-created) which enable connections between the servers in the cluster. Dedicated user created for each Juju unit/InnoDB Cluster member.
* `mysql_innodb_cs_#######` - the internal recovery user which enable connections between MySQl InnoDB Clusters in ClusterSet. One user is created for entire MySQL ClusterSet.

The full list of internal users is available in charm [source code](https://github.com/canonical/mysql-operator/blob/main/src/constants.py). The full dump of internal `mysql.user` table (on newly installed charm):

```shell
mysql> select Host,User,account_locked from mysql.user;
+-----------+---------------------------------+----------------+
| Host      | User                            | account_locked |
+-----------+---------------------------------+----------------+
| %         | backups                         | N              |
| %         | clusteradmin                    | N              |
| %         | monitoring                      | N              |
| %         | mysql_innodb_cluster_2277159043 | N              |
| %         | mysql_innodb_cluster_2277159122 | N              |
| %         | mysql_innodb_cluster_2277159949 | N              |
| %         | mysql_innodb_cs_f8ead780        | N              |
| %         | serverconfig                    | N              |
| localhost | mysql.infoschema                | Y              |
| localhost | mysql.session                   | Y              |
| localhost | mysql.sys                       | Y              |
| localhost | root                            | N              |
+-----------+---------------------------------+----------------+
10 rows in set (0.00 sec)
```
**Note**: it is forbidden to use/manage described above users! They are dedicated to the operators logic!
Please use [data-integrator](https://charmhub.io/mysql/docs/t-integrations) charm to generate/manage/remove an external credentials.

It is allowed to rotate passwords for *internal* users using action 'set-password'
```shell
> juju show-action mysql set-password
Change the system user's password, which is used by charm. It is for internal charm users and SHOULD NOT be used by applications.

Arguments
password:
  type: string
  description: The password will be auto-generated if this option is not specified.
username:
  type: string
  description: The username, the default value 'root'. Possible values - root,
    serverconfig, clusteradmin.
```

For example, to generate a new random password for *internal* user:

```shell
> juju run-action --wait mysql/leader set-password username=clusteradmin
unit-mysql-3:
  ...
  results: {}
  status: completed

> juju run-action --wait mysql/leader get-password username=clusteradmin
unit-mysql-3:
  ...
  results:
    password: PFLIwiwy0Pn7n7xgYtXKw39H
    username: clusteradmin
```from ..helpers import get_leader_unit, get_primary_unit_wrapper, retrieve_database_variable_value


To set a predefined password for the specific user, run:
```shell
> juju run-action --wait mysql/leader set-password username=clusteradmin password=newpassword
unit-mysql-0:
  ...
  results: {}
  status: completed

> juju run-action --wait mysql/leader get-password username=clusteradmin
unit-mysql-3:
  UnitId: mysql/3
  id: "14"
  results:
    password: newpassword
    username: clusteradmin
```
**Note**: the action `set-password` must be executed on juju leader unit (to update peer relation data with new value).

<a name="relation-users"></a>
## Relation/integration users explanations:

The operator created a dedicated user for every application related/integrated with database.
The username is composed by the relation ID and truncated uuid for the model, to ensure there is no
username clash in cross model relations. Usernames are limited to 32 chars as per [MySQL limit](https://dev.mysql.com/doc/refman/8.0/en/user-names.html).
Those users are removed on the juju relation/integration removal request. 
However, DB data stays in place and can be reused on re-created relations (using new user credentials):

```shell
mysql> select Host,User,account_locked from mysql.user where User like 'relation%';
+------+----------------------------+----------------+
| Host | User                       | account_locked |
+------+----------------------------+----------------+
| %    | relation-8_99200344b67b4e9 | N              |
| %    | relation-9_99200344b67b4e9 | N              |
+------+----------------------------+----------------+
2 row in set (0.00 sec)
```

The extra user(s) will be created for relation with [mysql-router](https://charmhub.io/mysql-router) charm to provide necessary users for applications related via mysql-router app:
```shell
mysql> select Host,User,account_locked from mysql.user where User like 'mysql_router%';
+------+----------------------------+----------------+
| Host | User                       | account_locked |
+------+----------------------------+----------------+
| %    | mysql_router1_gwa0oy6xnp8l | N              |
+------+----------------------------+----------------+
1 row in set (0.00 sec)
```

**Note**: If password rotation is needed for users used in relations, it is needed to remove the relation and create it again:
```shell
> juju remove-relation mysql myclientapp
> juju wait-for application mysql
> juju relate mysql myclientapp
```

<a name="extra-user-roles"></a>
### Extra user roles

When an application charm requests a new user through the relation/integration it can specify that the user should have the `admin` role in the `extra-user-roles` field. The `admin` role enables the new user to read and write to all databases (for the `mysql` system database it can only read data) and also to create and delete non-system databases.

**Note**: `extra-user-roles` is supported by modern interface `mysql_client` only and missing for legacy `mysql` interface. Read more about the supported charm interfaces [here](/t/10250).


<a name="admin-port"></a>
### Admin Port User Access

The charm mainly uses the `serverconfig` user for internal operations. For connections with this user, a special admin port is used (port `33062`), which enables the charm to operate MySQL even when users connections are saturated.
For further information on the administrative connection, refer to [MySQL docs](https://dev.mysql.com/doc/refman/8.0/en/administrative-connection-interface.html) on the topic.