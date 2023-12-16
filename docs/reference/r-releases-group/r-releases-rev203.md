# Charmed MySQL revision 203
> :warning: The revision is currently available in `8.0/candidate` only (**WIP**).
<!-- <sub>Monday, December 4, 2023</sub> -->

Dear community, this is to inform you that new Canonical Charmed MySQL is published in `8.0/stable` [charmhub](https://charmhub.io/mysql?channel=8.0/stable) channel for IAAS/VM.

## The features you can start using today:

* Add [profile-limit-memory](https://charmhub.io/mysql/configure?channel=8.0/edge#profile-limit-memory) option [[PR#331](https://github.com/canonical/mysql-operator/pull/331)][[DPE-2654](https://warthogs.atlassian.net/browse/DPE-2654)]
* Add [logrotation](https://charmhub.io/mysql/docs/e-logs?channel=8.0/edge) for general/error/slowquery text logs [[PR#329](https://github.com/canonical/mysql-operator/pull/329)][[DPE-1796](https://warthogs.atlassian.net/browse/DPE-1796)]
* Use labels for internal Juju secrets in [[PR#348](https://github.com/canonical/mysql-operator/pull/348)][[DPE-2886](https://warthogs.atlassian.net/browse/DPE-2886)]
* Updated data-platform-libs for external secrets [[PR#333](https://github.com/canonical/mysql-operator/pull/333)]
* All the functionality from [the previous revisions](/t/11881)

## Bugfixes included:

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/mysql-operator/issues) platforms.<br/>[GitHub Releases](https://github.com/canonical/mysql-operator/releases) provide a detailed list of bugfixes/PRs/Git commits for each revision.<br/>Highlights for the current revision:

* Fixed single unit upgrade [[PR#340](https://github.com/canonical/mysql-operator/pull/340)][[DPE-2662](https://warthogs.atlassian.net/browse/DPE-2662)]
* Fixed dateformat in logrotate config to avoid causing filename conflicts after 24hrs of uptime [[PR#363](https://github.com/canonical/mysql-operator/pull/363)][[DPE-3063](https://warthogs.atlassian.net/browse/DPE-3063)]
* Stops logging FLUSH LOG statements to the MySQL binlog which is causing GTID conflicts and prevents the member from self-healing [[PR#336](https://github.com/canonical/mysql-operator/pull/336)]

## What is inside the charms:

* Charmed MySQL ships the latest MySQL “8.0.34-0ubuntu0.22.04.1”
* CLI mysql-shell updated to "8.0.34-0ubuntu0.22.04.1~ppa1"
* Backup tools xtrabackup/xbcloud  updated to "8.0.34-29"
* The Prometheus mysqld-exporter is "0.14.0-0ubuntu0.22.04.1~ppa1"
* VM charms based on [Charmed MySQL](https://snapcraft.io/charmed-mysql) SNAP (Ubuntu LTS “22.04” - ubuntu:22.04-based) revision 69
* Principal charms supports the latest LTS series “22.04” only
* Subordinate charms support LTS “22.04” and “20.04” only

## Technical notes:

* Upgrade (`juju refresh`) is possible from this revision 196+
* Use this operator together with a modern operator "[MySQL Router](https://charmhub.io/mysql-router?channel=dpe/beta)"
* Please check additionally [the previously posted restrictions](/t/11881)

## How to reach us:

If you would like to chat with us about your use-cases or ideas, you can reach us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/data-platform) or [Discourse](https://discourse.charmhub.io/). Check all other contact details [here](/t/11867).

Consider [opening a GitHub issue](https://github.com/canonical/mysql-operator/issues) if you want to open a bug report.<br/>[Contribute](https://github.com/canonical/mysql-operator/blob/main/CONTRIBUTING.md) to the project!

## Hints:

Please check [all the previous release notes](/t/11881) if you are jumping over the several stable revisions!