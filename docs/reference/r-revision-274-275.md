> Reference > Release Notes > [All releases][] > Revision 274/275

# Revision 274/275
<sub>TODO</sub>

[note type="caution"]
This page is a work in progress for a future release.
[/note]

Dear community,

Canonical's newest Charmed MySQL operator has been published in the [8.0/stable channel].

Due to the newly added support for arm64 architecture, the MySQL charm now releases two revisions simultaneously:
* Revision 275 is built for `amd64`
* Revision 274 is built for `arm64`

To make sure you deploy for the right architecture, we recommend setting an [architecture constraint](https://juju.is/docs/juju/constraint#heading--arch) for your entire Juju model.

Otherwise, you can specify the architecture at deploy time with the `--constraints` flag as follows:

```shell
juju deploy mysql --constraints arch=<arch>
```
where `<arch>` can be `amd64` or `arm64`.

[note]
This release of Charmed MySQL requires Juju `v.3.4.3` or `3.5.2+`. See the [Technical details](#technical-details) section for more information.
[/note]

---

## Highlights

Below is an overview of the major highlights, enhancements, and bugfixes in this revision. For a detailed list of all commits since the last stable release, see the [GitHub release notes].

### Enhancements
* Upgraded MySQL from `v8.0.36` -> `v8.0.37` (see [Packaging](#packaging))
* Added support or ARM64 architecture ([PR #472](https://github.com/canonical/mysql-operator/pull/472)) 
* Added support for Audit plugin ([PR #488](https://github.com/canonical/mysql-operator/pull/488)) ([DPE-4366](https://warthogs.atlassian.net/browse/DPE-4366))
* Added support for rescanning cluster for unit rejoin after node drain ([PR #462](https://github.com/canonical/mysql-operator/pull/462)) ([DPE-4118](https://warthogs.atlassian.net/browse/DPE-4118))
* Added Awesome Prometheus Alert Rules ([PR #493](https://github.com/canonical/mysql-operator/pull/493)) ([DPE-2477](https://warthogs.atlassian.net/browse/DPE-2477))
* Changeed binlog retention period (one week by default) ([PR #503](https://github.com/canonical/mysql-operator/pull/503)) ([DPE-4247](https://warthogs.atlassian.net/browse/DPE-4247))

### Bugfixes

* Removed passwords from outputs and tracebacks ([PR #499](https://github.com/canonical/mysql-operator/pull/499)) ([DPE-4266](https://warthogs.atlassian.net/browse/DPE-4266))
* Fixed cluster metadata and instance state checks ([PR #482](https://github.com/canonical/mysql-operator/pull/482)) ([DPE-4850](https://warthogs.atlassian.net/browse/DPE-4850))
* Ensure username uniqueness ([PR #464](https://github.com/canonical/mysql-operator/pull/464)) ([DPE-4643](https://warthogs.atlassian.net/browse/DPE-4643))
* Set instance offline mode on restore ([PR #478](https://github.com/canonical/mysql-operator/pull/478)) ([DPE-4699](https://warthogs.atlassian.net/browse/DPE-4699))
* Added support for re-scanning cluster for unit rejoin after node drain ([PR #462](https://github.com/canonical/mysql-operator/pull/462)) ([DPE-4118](https://warthogs.atlassian.net/browse/DPE-4118))
* Fixes for backup logging ([PR #471](https://github.com/canonical/mysql-operator/pull/471)) ([DPE-4699](https://warthogs.atlassian.net/browse/DPE-4699))
* Fixed global-primary on endpoint ([PR #467](https://github.com/canonical/mysql-operator/pull/467)) ([DPE-4658](https://warthogs.atlassian.net/browse/DPE-4658))

## Technical details
This section contains some technical details about the charm's contents and dependencies. 

If you are jumping over several stable revisions, check [previous release notes][All releases] before upgrading.

## Requirements and compatibility
This charm revision features the following changes in dependencies:
* (increased) MySQL version `v8.0.37`

> This release of Charmed MySQL requires Juju `v.3.4.3` or `3.5.2+`. See the guide [How to upgrade Juju for a new database revision].

See the [system requirements] page for more details about software and hardware prerequisites.

### Integration tests
Below are the charm integrations tested with this revision on different Juju environments and architectures:
* Juju `v2.9.49` on `amd64`
* Juju  `v3.4.4` on `amd64` and `arm64`

**Juju `v2.9.49` on `amd64`:**

| Software | Version | |
|-----|-----|-----|
| [tls-certificates-operator] | `rev 22`, `legacy/stable` | 

**Juju `v3.4.4` on `amd64` and `arm64`:**
| Software | Version | |
|-----|-----|-----|
| [self-signed-certificates] | `rev 155`, `latest/stable` | 

**All:**
| Software | Version |  |
|-----|-----|-----|
| [lxd] | `5.12/stable` | |
| [landscape-client] | `rev69` | |
| [ubuntu-advantage] | `rev95` | |
| [s3-integrator] | `rev31` | |
| [mysql-test-app] |  `0.0.2` | |

See the [`/lib/charms` directory on GitHub] for a full list of supported libraries.

See the [Integrations tab] for a full list of supported integrations/interfaces/endpoints.

### Packaging
This charm is based on the [`charmed-mysql` snap] Revision [113/114][snap rev113/114]. It packages:
- mysql-server-8.0: [8.0.37-0ubuntu0.22.04.1]
- mysql-router `v8.0.37`: [8.0.37-0ubuntu0.22.04.1]
- mysql-shell `v8.0.37`: [8.0.37+dfsg-0ubuntu0.22.04.1~ppa3]
- prometheus-mysqld-exporter `v0.14.0`: [0.14.0-0ubuntu0.22.04.1~ppa2]
- prometheus-mysqlrouter-exporter `v5.0.1`: [5.0.1-0ubuntu0.22.04.1~ppa1]
- percona-xtrabackup `v8.0.35`: [8.0.35-31-0ubuntu0.22.04.1~ppa3]

## Contact us
  
Charmed MySQL is an open source project that warmly welcomes community contributions, suggestions, fixes, and constructive feedback.  
* Raise software issues or feature requests on [**GitHub**](https://github.com/canonical/mysql-operator/issues)  
*  Report security issues through [**Launchpad**](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File)  
* Contact the Canonical Data Platform team through our [Matrix](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) channel.

<!-- LINKS -->
[8.0/stable channel]: https://charmhub.io/mysql?channel=8.0/stable 
[GitHub release notes]: https://github.com/canonical/mysql-operator/releases/tag/rev275

[All releases]: /t/11881
[system requirements]: /t/11742
[How to upgrade Juju for a new database revision]: /t/14325

[Integrations tab]: https://charmhub.io/mysql/integrations
[Libraries tab]: https://charmhub.io/mysql/libraries

[`/lib/charms` directory on GitHub]: https://github.com/canonical/mysql-operator/tree/main/lib/charms

[juju]: https://juju.is/docs/juju/
[lxd]: https://documentation.ubuntu.com/lxd/en/latest/
[data-integrator]: https://charmhub.io/data-integrator
[s3-integrator]: https://charmhub.io/s3-integrator
[microk8s]: https://charmhub.io/microk8s
[tls-certificates-operator]: https://charmhub.io/tls-certificates-operator
[self-signed-certificates]: https://charmhub.io/self-signed-certificates
[mysql-test-app]: https://charmhub.io/mysql-test-app
[landscape-client]: https://charmhub.io/landscape-client
[ubuntu-advantage]: https://charmhub.io/ubuntu-advantage

[snap rev113/114]: https://github.com/canonical/charmed-mysql-snap/releases/tag/rev114
[`charmed-mysql` snap]: https://snapcraft.io/charmed-mysql
[8.0.37-0ubuntu0.22.04.1]: https://launchpad.net/ubuntu/+source/mysql-8.0/8.0.37-0ubuntu0.22.04.3
[8.0.37+dfsg-0ubuntu0.22.04.1~ppa3]: https://launchpad.net/~data-platform/+archive/ubuntu/mysql-shell
[0.14.0-0ubuntu0.22.04.1~ppa2]: https://launchpad.net/~data-platform/+archive/ubuntu/mysqld-exporter
[5.0.1-0ubuntu0.22.04.1~ppa1]: https://launchpad.net/~data-platform/+archive/ubuntu/mysqlrouter-exporter
[8.0.35-31-0ubuntu0.22.04.1~ppa3]: https://launchpad.net/~data-platform/+archive/ubuntu/xtrabackup