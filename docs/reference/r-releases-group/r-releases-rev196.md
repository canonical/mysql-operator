# Charmed MySQL revision 196
<sub>September 29, 2023</sub>

Dear community, this is to inform you that new Canonical Charmed MySQL is published in `8.0/stable` [charmhub](https://charmhub.io/mysql?channel=8.0/stable) channel for IAAS/VM.

## The features you can start using today:

* [Add Juju 3 support](/t/11742) (Juju 2 is still supported) [[DPE-1790](https://warthogs.atlassian.net/browse/DPE-1790)]
* Peer secrets are now stored in [Juju secrets](https://juju.is/docs/juju/manage-secrets) [[DPE-1812](https://warthogs.atlassian.net/browse/DPE-1812)]
* Charm [minor upgrades](/t/11748) and [minor rollbacks](/t/11749) [[DPE-2206](https://warthogs.atlassian.net/browse/DPE-2206)]
* [Profiles configuration](/t/11973) support [[DPE-2154](https://warthogs.atlassian.net/browse/DPE-2154)]
* Workload updated to [MySQL 8.0.34](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-34.html) [[DPE-2425](https://warthogs.atlassian.net/browse/DPE-2425)]
* Support `juju expose` [[DPE-1214](https://warthogs.atlassian.net/browse/DPE-1214)]
* Switch to [MySQL ClusterSet](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-clusterset.html) by default [[DPE-1231](https://warthogs.atlassian.net/browse/DPE-1231)]
* Add the first Prometheus alert rule (COS Loki) [[PR#230](https://github.com/canonical/mysql-operator/pull/230)]
* UX: Autogenerate db/user in legacy mysql (if not specified as config) [[DPE-1511](https://warthogs.atlassian.net/browse/DPE-1511)]
* Switch Charmed MySQL SNAP to [Canonical binaries](https://launchpad.net/~data-platform)
* New documentation:
  * [Architecture (HLD/LLD)](/t/11756)
  * [Upgrade section](/t/11745)
  * [Release Notes](/t/11881)
  * [Requirements](/t/11742)
  * [Users](/t/10789)
  * [Statuses](/t/10624)
  * [Development](/t/11889)
  * [Testing reference](/t/11770)
  * [Legacy charm](/t/10788)
  * [Contacts](/t/11867)
* All the functionality from [the previous revisions](/t/11882)

## Bugfixes included:

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/mysql-operator/issues) platforms.<br/>[GitHub Releases](https://github.com/canonical/mysql-operator/releases) provide a detailed list of bugfixes/PRs/Git commits for each revision.<br/>Highlights for the current revision:

* [#209](https://github.com/canonical/mysql-operator/pull/209) Use special user for backups + miscellaneous backups fixes
* [#216](https://github.com/canonical/mysql-operator/pull/216) Fix/join units refactor by 
* [#223](https://github.com/canonical/mysql-operator/pull/223) Add auto-tuning for max_connections
* [#224](https://github.com/canonical/mysql-operator/pull/224) Optimize mysqlsh calls on library by 
* [#254](https://github.com/canonical/mysql-operator/pull/254) Miscellaneous improvements to the mysql legacy relation
* [#296](https://github.com/canonical/mysql-operator/pull/296) Fixed MySQL memory allocation, consider 'group_replication_message_cache_size'
* [DPE-1626](https://warthogs.atlassian.net/browse/DPE-1626) Add timeout kwarg to run_mysqlcli_script
* [DPE-2215](https://warthogs.atlassian.net/browse/DPE-2215) Fix wait timeout for shared-db
* [DPE-2089](https://warthogs.atlassian.net/browse/DPE-2089) Improve charm to add snap alias charmed-mysql.mysql -> mysql
* [DPE-2352](https://warthogs.atlassian.net/browse/DPE-2352) Restart mysql exporter upon monitoring password change
* [DPE-1979](https://warthogs.atlassian.net/browse/DPE-1979) Fixed machine deployments where hosts are not resolvable
* [DPE-1519](https://warthogs.atlassian.net/browse/DPE-1519) Stabilized integration with mysql-route
* [DPE-2455](https://warthogs.atlassian.net/browse/DPE-2455) Fix bug that caused unnecessary truncation of the mysql hosts cache
* [DPE-2214](https://warthogs.atlassian.net/browse/DPE-2214) Avoid resetting workload if recovery from unreachable state unsuccessful
* [DPE-2478](https://warthogs.atlassian.net/browse/DPE-2478) Use actual observer pid in databag + reduce volume of secrets related logs
* [DPE-2217](https://warthogs.atlassian.net/browse/DPE-2217) Preemptively switch primary on scale-down
* [DPE-2401](https://warthogs.atlassian.net/browse/DPE-2401) Hold snap revision by default
* [DPE-2485](https://warthogs.atlassian.net/browse/DPE-2485) Resolve race condition when restarting after configure_instance
* [DPE-988](https://warthogs.atlassian.net/browse/DPE-988) Fixed standby units (9+ cluster members are waiting to join the cluster)
* [DPE-2177](https://warthogs.atlassian.net/browse/DPE-2177) Stop configuring mysql user `root@%` (removed as no longer necessary)

## What is inside the charms:

* Charmed MySQL ships the latest MySQL “8.0.34-0ubuntu0.22.04.1”
* CLI mysql-shell updated to "8.0.34-0ubuntu0.22.04.1~ppa1"
* Backup tools xtrabackup/xbcloud  updated to "8.0.34-29"
* The Prometheus mysqld-exporter is "0.14.0-0ubuntu0.22.04.1~ppa1"
* VM charms based on [Charmed MySQL](https://snapcraft.io/charmed-mysql) SNAP (Ubuntu LTS “22.04” - ubuntu:22.04-based)
* Principal charms supports the latest LTS series “22.04” only.
* Subordinate charms support LTS “22.04” and “20.04” only.

## Technical notes:

* Upgrade (`juju refresh`) from the old-stable revision 151 to the current-revision 196 is **NOT** supported!!! The [upgrade](/t/11745) functionality is new and supported for revision 196+ only!

Please check additionally [the previously posted restrictions](/t/11882).

## How to reach us:

If you would like to chat with us about your use-cases or ideas, you can reach us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/data-platform) or [Discourse](https://discourse.charmhub.io/). Check all other contact details [here](/t/11867).

Consider [opening a GitHub issue](https://github.com/canonical/mysql-operator/issues) if you want to open a bug report.<br/>[Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) to the project!

## Hints:

Please check [all the previous release notes](/t/11882) if you are jumping over the several stable revisions!