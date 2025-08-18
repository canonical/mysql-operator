# Profiles

Charmed MySQL's usage of resources depends on the chosen profile:

```shell
juju deploy mysql --config profile=<profile>
```

## Profile values

| Value | Description | Details |
| --- | --- | ----- |
|`production`<br>(default)|[Maximum performance]| ~75% of [unit] memory granted for MySQL<br/>`max_connections`= [RAM / 12MiB] (max safe value)|
|`testing`|[Minimal resource usage]| `innodb_buffer_pool_size` = 20MB<br/> `innodb_buffer_pool_chunk_size`=1MB<br/> `group_replication_message_cache_size`=128MB<br/>`max_connections`=100<br/> `performance-schema-instrument`='memory/%=OFF' |

You can also see all MySQL charm configuration options on [Charmhub](https://charmhub.io/mysql/configure#profile).

## Change profile

<!--TODO: check if done.
**Note**: Pre-deployed application profile change is [planned](https://warthogs.atlassian.net/browse/DPE-2404) but currently is NOT supported. -->

To change the profile, use the [`juju config` command](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/config/). For example:

```shell
juju deploy mysql --config profile=testing && \
juju config mysql profile=production
```

## Juju constraints

[Juju constraints](https://juju.is/docs/juju/constraint) allows setting RAM/CPU limits for [units](https://juju.is/docs/juju/unit):

```shell
juju deploy mysql --constraints cores=8 mem=16G
```

Juju constraints can be set together with the charm profile:

```shell
juju deploy mysql --constraints cores=8 mem=16G --config profile=testing
```

<!-- Links -->

[Maximum performance]: https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py#L766-L775

[unit]: https://juju.is/docs/juju/unit

[RAM / 12MiB]: https://github.com/canonical/mysql-operator/blob/53e54745f47b6d2184c54386ee984792cb939152/lib/charms/mysql/v0/mysql.py#L2092

[Minimal resource usage]: https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py#L759-L764
