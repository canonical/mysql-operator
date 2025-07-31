# Charm testing reference

> **:information_source: Hint**: Use [Juju 3](/). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

There are [a lot of test types](https://en.wikipedia.org/wiki/Software_testing) available and most of them are well applicable for Charmed MySQL. Here is a list prepared by Canonical:

* Smoke test
* Unit tests
* Integration tests
* System test
* Performance test

## Smoke test

[u]Complexity[/u]: trivial<br/>
[u]Speed[/u]: fast<br/>
[u]Goal[/u]: ensure basic functionality works over short amount of time.

[Setup an Juju 3.x environment](/tutorial/1-set-up-the-environment), deploy DB with test application and start "continuous write" test:
```shell
juju add-model smoke-test

juju deploy mysql --channel 8.0/edge --config profile=testing
juju add-unit mysql -n 2 # (optional)

juju deploy mysql-test-app --channel latest/edge
juju relate mysql-test-app mysql:database

# Make sure random data inserted into DB by test application:
juju run mysql-test-app/leader get-inserted-data

# Start "continuous write" test:
juju run mysql-test-app/leader start-continuous-writes
export password=$(juju run mysql/leader get-password username=root | yq '.. | select(. | has("password")).password')
watch -n1 -x juju ssh mysql/leader "mysql -h 127.0.0.1 -uroot -p${password} -e \"select count(*) from continuous_writes_database.data\""

# Watch the counter is growing!
```
[u]Expected results[/u]:

* mysql-test-app continuously inserts records in database `continuous_writes_database` table `data`.
* the counters (amount of records in table) are growing on all cluster members

[u]Hints[/u]:
```shell
# Stop "continuous write" test
juju run mysql-test-app/leader stop-continuous-writes

# Truncate "continuous write" table (delete all records from DB)
juju run mysql-test-app/leader clear-continuous-writes
```

## Unit tests

Please check the "[Contributing](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md#testing)" guide and follow `tox run -e unit` examples there.

## Integration tests

Please check the "[Contributing](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md#testing)" guide and follow `tox run -e integration` examples there.

## System test

Please check/deploy the charm [mysql-bundle](https://charmhub.io/mysql-bundle) ([Git](https://github.com/canonical/mysql-bundle)). It deploy and test all the necessary parts at once.

## Performance test
Refer to the [sysbench documentation](https://discourse.charmhub.io/t/charmed-sysbench-documentation-home/13945).

