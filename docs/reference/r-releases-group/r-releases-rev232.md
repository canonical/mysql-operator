>Reference > Release Notes > [All revisions](/t/11881) > Revision 232  
# Revision 232 (WIP)
  
<sub>DD, MM, YYYY</sub>
  
Dear community,
  
We'd like to announce that Canonical's newest Charmed MySQL operator has been published in the '8.0/stable' [channel](https://charmhub.io/mysql/docs/r-releases?channel=8.0/stable) :tada:
  
[note]
If you are jumping over several stable revisions, make sure to check [previous release notes](/t/11881) before upgrading to this revision.
[/note]  
  
## Features you can start using today
  
* Feature ([PR#XXX]())  
* Feature ([DPE-XXX]())  
  
## Bugfixes
  
* ...
  
Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/mysql-operator/issues) platforms.  
[GitHub Releases](https://github.com/canonical/mysql-operator/releases) provide a detailed list of bugfixes, PRs, and commits for each revision.  
  
## Inside the charms
  
* Charmed MySQL ships the latest MySQL "8.0.36-0ubuntu0.22.04.1"
* CLI mysql-shell updated to "8.0.36+dfsg-0ubuntu0.22.04.1~ppa4"
* Backup tools xtrabackup/xbcloud updated to "8.0.35-30"
* The Prometheus mysqld-exporter is "0.14.0-0ubuntu0.22.04.1~ppa2"
* VM charms [based on Charmed MySQL SNAP](https://github.com/canonical/charmed-mysql-snap) (Ubuntu LTS "22.04" - ubuntu:22.04-based) revision 103
* Principal charms supports the latest LTS series "22.04" only
* Subordinate charms support LTS "22.04" and "20.04" only
  
## Technical notes
  
* ...  
  
## Contact us
  
Charmed MySQL is an open source project that warmly welcomes community contributions, suggestions, fixes, and constructive feedback.  
* Raise software issues or feature requests on [**GitHub**](https://github.com/canonical/mysql-operator/issues)  
*  Report security issues through [**Launchpad**](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File)  
* Contact the Canonical Data Platform team through our [Matrix](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) channel.