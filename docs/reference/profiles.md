# Profiles

> **Warning:** The feature is currently available in the channel `8.0/candidate` only (revision 186+) and will be released to the channel `8.0/stable` soon.

Charmed MySQL resource utilization depends on the chosen profile:

```shell
juju deploy mysql --config profile=testing
```

## Profile values

|Value|Description|Tech details|
| --- | --- | ----- |
|`production`<br>(default)|[Maximum performance](https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py#L766-L775)| ~75% of [unit memory](https://juju.is/docs/juju/unit) granted for MySQL<br/>max_connections=[RAM/12MiB](https://github.com/canonical/mysql-operator/blob/53e54745f47b6d2184c54386ee984792cb939152/lib/charms/mysql/v0/mysql.py#L2092) (max safe value)|
|`testing`|[Minimal resource usage](https://github.com/canonical/mysql-operator/blob/main/lib/charms/mysql/v0/mysql.py#L759-L764)| innodb_buffer_pool_size = 20MB<br/>innodb_buffer_pool_chunk_size=1MB<br/>group_replication_message_cache_size=128MB<br/>max_connections=100<br/>performance-schema-instrument='memory/%=OFF' |

## Config change

> :warning: **Note**: Pre-deployed application profile change is [planned](https://warthogs.atlassian.net/browse/DPE-2404) but currently is NOT supported.

To change the profile, use `juju config` ([see all charm configs](https://charmhub.io/mysql/configure#profile)):
```shell
juju deploy mysql --config profile=testing && \
juju config mysql profile=production
```

## Juju Constraints

[Juju constraints](https://juju.is/docs/juju/constraint) allows RAM/CPU limits for [Juju units](https://juju.is/docs/juju/unit):

```shell
juju deploy mysql --constraints cores=8 mem=16G
```

Juju constraints can be used together with charm profile:

```shell
juju deploy mysql --constraints cores=8 mem=16G --config profile=testing
```

