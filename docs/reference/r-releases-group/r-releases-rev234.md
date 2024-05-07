>Reference > Release Notes > [All revisions](/t/11881) > Revision 234
# Revision 234 (`8.0/candidate` only)
  
<sub>DD, MM, YYYY</sub>
  
Dear community,
  
We'd like to announce that Canonical's newest Charmed MySQL operator has been published in the '8.0/stable' [channel](https://charmhub.io/mysql/docs/r-releases?channel=8.0/stable) :tada:
  
[note]
If you are jumping over several stable revisions, make sure to check [previous release notes](/t/11881) before upgrading to this revision.
[/note]  
  
## Features you can start using today

* New workload version [MySQL 8.0.36](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-36.html)
* Async replication between clouds [[PR#375](https://github.com/canonical/mysql-operator/pull/375)][[DPE-2957](https://warthogs.atlassian.net/browse/DPE-2957)]
* TLS CA chain support [[PR#396](https://github.com/canonical/mysql-operator/pull/396)]
* [profile-limit-memory](https://charmhub.io/mysql/configure?channel=8.0/edge#profile-limit-memory) option [[PR#331](https://github.com/canonical/mysql-operator/pull/331)][[DPE-2654](https://warthogs.atlassian.net/browse/DPE-2654)]
* [log rotation](https://charmhub.io/mysql/docs/e-logs?channel=8.0/edge) for general/error/slowquery text logs [[PR#329](https://github.com/canonical/mysql-operator/pull/329)][[DPE-1796](https://warthogs.atlassian.net/browse/DPE-1796)]
* Labels for internal Juju secrets in [[PR#348](https://github.com/canonical/mysql-operator/pull/348)][[DPE-2886](https://warthogs.atlassian.net/browse/DPE-2886)]
* Internal disable operator mode [[DPE-2184](https://warthogs.atlassian.net/browse/DPE-2184)]
* Updated `data-platform-libs` for external secrets [[PR#333](https://github.com/canonical/mysql-operator/pull/333)]
* Snap aliases for MySQL server / Router [[PR#417](https://github.com/canonical/mysql-operator/pull/417)][[DPE-3702](https://warthogs.atlassian.net/browse/DPE-3702)]
* Support for subordination with `ubuntu-advantage` and `landscape-client` [[PR#413](https://github.com/canonical/mysql-operator/pull/413)]
* [Allure Report](https://canonical.github.io/mysql-operator/) [[PR#391](https://github.com/canonical/mysql-operator/pull/391)]
* All the functionality from [the previous revisions](/t/11881)
  
## Bugfixes
 
*  Fixed MAAS deployment [[PR#444](https://github.com/canonical/mysql-operator/pull/444)][[DPE-3115](https://warthogs.atlassian.net/browse/DPE-3115)]
* Fixed single unit upgrade [[PR#340](https://github.com/canonical/mysql-operator/pull/340)][[DPE-2662](https://warthogs.atlassian.net/browse/DPE-2662)]
* Fixed dateformat in logrotate config to avoid causing filename conflicts after 24hrs of uptime [[PR#363](https://github.com/canonical/mysql-operator/pull/363)][[DPE-3063](https://warthogs.atlassian.net/browse/DPE-3063)]
* Stops logging FLUSH LOG statements to the MySQL binlog which is causing GTID conflicts and prevents the member from self-healing [[PR#336](https://github.com/canonical/mysql-operator/pull/336)]
* Fixed rollback for unsupported MySQL datadir [[DPE-3392](https://warthogs.atlassian.net/browse/DPE-3392)]
* Updated TLS test lib and test charm [[PR#392](https://github.com/canonical/mysql-operator/pull/392)][[DPE-3403](https://warthogs.atlassian.net/browse/DPE-3403)]
* Fixed floor value for max_connections [[PR#398](https://github.com/canonical/mysql-operator/pull/398)]
* Fixed KeyError when no ca-chain [[PR#403](https://github.com/canonical/mysql-operator/pull/403)][[DPE-3688](https://warthogs.atlassian.net/browse/DPE-3688)]
* Fixed broken state (after the restart) [[PR#381](https://github.com/canonical/mysql-operator/pull/381)][[DPE-2618](https://warthogs.atlassian.net/browse/DPE-2618)]
* Fixed error messaging when no bucket for backup [[PR#350](https://github.com/canonical/mysql-operator/pull/350)][[DPE-2758](https://warthogs.atlassian.net/browse/DPE-2758)]
* Avoid setting secret upon TLS relation broken if using juju secrets [[PR#360](https://github.com/canonical/mysql-operator/pull/360)][[DPE-2677](https://warthogs.atlassian.net/browse/DPE-2677)]
* Fixed logrotate file path [[PR#374](https://github.com/canonical/mysql-operator/pull/374)]
*  Started using labels for internal secrets [[PR#348](https://github.com/canonical/mysql-operator/pull/348)][[DPE-2886](https://warthogs.atlassian.net/browse/DPE-2886)]

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/mysql-operator/issues) platforms.  
[GitHub Releases](https://github.com/canonical/mysql-operator/releases) provide a detailed list of bugfixes, PRs, and commits for each revision.  
  
## Inside the charms
  
* Charmed MySQL ships the latest MySQL `8.0.36-0ubuntu0.22.04.1`
* `mysql-shell` CLI tool updated to `8.0.36+dfsg-0ubuntu0.22.04.1~ppa4`
* Backup tools xtrabackup/xbcloud updated to `8.0.35-30`
* The Prometheus mysqld-exporter is `0.14.0-0ubuntu0.22.04.1~ppa2`
* VM charms [based on Charmed MySQL snap](https://github.com/canonical/charmed-mysql-snap) (Ubuntu LTS `22.04.4`) revision `103`
* Principal charms supports Ubuntu LTS series 22.04 only
  
## Technical notes
  
* Upgrade (`juju refresh`) is possible from revision 196+
* Use this operator together with a modern operator [MySQL Router](https://charmhub.io/mysql-router?channel=dpe/beta)
* Please check restrictions from [previous release notes](/t/11881)
  
## Contact us
  
Charmed MySQL is an open source project that warmly welcomes community contributions, suggestions, fixes, and constructive feedback.  
* Raise software issues or feature requests on [**GitHub**](https://github.com/canonical/mysql-operator/issues)  
*  Report security issues through [**Launchpad**](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File)  
* Contact the Canonical Data Platform team through our [Matrix](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) channel.