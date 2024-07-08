# How to manage related applications
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju integrate` with `juju relate` for Juju 2.9.

## New `mysql_client` interface:

Relations to new applications are supported via the "[mysql_client](https://github.com/canonical/charm-relation-interfaces/blob/main/interfaces/mysql_client/v0/README.md)" interface. To create a relation:

```shell
juju integrate mysql application
```

To remove a relation:

```shell
juju remove-relation mysql application
```

## Legacy `mysql` interface:

We have also added support for the database legacy relation via the `mysql` interface. Please note that these interface is deprecated.

 ```shell
juju integrate mysql:mysql wordpress
```

Also extended permissions can be requested using `mysql-root` edpoint:
```shell
juju integrate mysql:mysql-root wordpress
```


## Rotate applications password

To rotate the passwords of users created for related applications, the relation should be removed and related again. That process will generate a new user and password for the application.

```shell
juju remove-relation application mysql
juju integrate application mysql
```

### Internal operator user

The operator user is used internally by the Charmed MySQL Operator, the `set-password` action can be used to rotate its password.

* To set a specific password for the operator user

```shell
juju run mysql/leader set-password password=<password>
```

* To randomly generate a password for the operator user

```shell
juju run mysql/leader set-password
```