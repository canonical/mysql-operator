# Releases

This page provides high-level overviews of the dependencies and features that are supported by each revision in every stable release.

To learn more about the different release tracks and channels, see the [Juju documentation about channels](https://juju.is/docs/juju/channel#heading--risk).

To see all releases and commits, check the [Charmed MySQL Releases page on GitHub](https://github.com/canonical/mysql-operator/releases).

## Dependencies and supported features

For a given release, this table shows:
* The MySQL version packaged inside
* The minimum Juju version required to reliably operate **all** features of the release
   > This charm still supports older versions of Juju down to 2.9. See the [Juju section of the system requirements](/t/11742) for more details.
* Support for specific features

| Release | MySQL version | Juju version | [TLS encryption](/t/9898)* | [COS monitoring](/t/9900) | [Minor version upgrades](/t/11748) | [Cross-regional async replication](/t/14169) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| [312], [313] | 8.0.39 | `3.4.3+` | ![check] | ![check] | ![check] | ![check] |
| [240] | 8.0.36 | `3.4.3+` | ![check] | ![check] | ![check] | ![check] |
| [196] | 8.0.34 | `3.1.6+` |  | ![check] | ![check] |  |
| [151] | 8.0.32 | `2.9.32+` |  | ![check] | ![check] |  |

\* **TLS encryption**: Support for **`v2` or higher** of the [`tls-certificates` interface](https://charmhub.io/tls-certificates-interface/libraries/tls_certificates). This means that you can integrate with [modern TLS charms](https://charmhub.io/topics/security-with-x-509-certificates).

>For more details about a particular revision, refer to its dedicated Release Notes page.
For more details about each feature/interface, refer to the documentation linked in the column headers.

## Architecture and base
Several [revisions](https://juju.is/docs/sdk/revision) are released simultaneously for different [bases/series](https://juju.is/docs/juju/base) using the same charm code. In other words, one release contains multiple revisions.

> If you do not specify a revision on deploy time, Juju will automatically choose the revision that matches your base and architecture.

> If you deploy a specific revision, **you must make sure it matches your base and architecture** via the tables below or with [`juju info`](https://juju.is/docs/juju/juju-info)


### Release 312-313

| Revision | amd64 | arm64 | Ubuntu 22.04 LTS
|:--------:|:-----:|:-----:|:-----:|
|[313]  |![check] | | ![check]  |
|[312] |  | ![check]| ![check] |

[details=Older releases]

### Release 240

| Revision | amd64 | arm64 | Ubuntu 22.04 LTS
|:--------:|:-----:|:-----:|:-----:|
|[240] |![check]| | ![check]   |

### Release 196

| Revision | amd64 | arm64 | Ubuntu 22.04 LTS
|:--------:|:-----:|:-----:|:-----:|
|[196] |![check]| | ![check]   |

### Release 151

| Revision | amd64 | arm64 | Ubuntu 22.04 LTS
|:--------:|:-----:|:-----:|:-----:|
|[151] |![check]| | ![check]   |

[/details]

[note]
 Our release notes are an ongoing work in progress. If there is any additional information about releases that you would like to see or suggestions for other improvements, don't hesitate to contact us on [Matrix ](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) or leave a comment.
[/note]

<!-- LINKS -->

[313]: https://github.com/canonical/mysql-operator/releases/tag/rev312
[312]: https://github.com/canonical/mysql-operator/releases/tag/rev312
[240]: https://github.com/canonical/mysql-operator/releases/tag/rev240
[196]: https://github.com/canonical/mysql-operator/releases/tag/rev196
[151]: https://github.com/canonical/mysql-operator/releases/tag/rev151

<!--BADGES-->
[check]: https://img.icons8.com/color/20/checkmark--v1.png