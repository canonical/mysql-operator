# Juju 

[Juju](https://juju.is/) is an open source orchestration engine for software operators that enables the deployment, integration and lifecycle management of applications at any scale, on any infrastructure using charms.

This [charm](https://charmhub.io/mysql) is an operator - business logic encapsulated in reusable software packages that automate every aspect of an application's life. Charms are shared via [CharmHub](https://charmhub.io/).

See also:

* [Juju Documentation](https://juju.is/docs/juju) and [Blog](https://ubuntu.com/blog/tag/juju)
* [Charm SDK](https://juju.is/docs/sdk)

This page aims to provide some context on some of the inner workings of Juju that affect this charm.

## Summary
* [Breaking changes between Juju 2.8.x and 3.x](#heading--breaking-changes)
* [Juju upgrades](#heading--upgrades)

---
<a href="#heading--breaking-changes"><h2 id="heading--breaking-changes"> Breaking changes between Juju 2.9.x and 3.x </h2></a>

As this charm documentation is written for Juju 3.x, users of 2.9.x will encounter noteworthy changes when following the instructions. This section explains those changes.

Breaking changes have been introduced in the Juju client between versions 2.9.x and 3.x. These are caused by the renaming and re-purposing of several commands - functionality and command options remain unchanged.

In the context of this guide, the pertinent changes are shown here:

|2.9.x|3.x|
| --- | --- |
|`add-relation`|`integrate`|
|`relate`|`integrate`|
|`run`|`exec`|
|`run-action --wait`|`run`|

See the [Juju 3.0 release notes](https://juju.is/docs/juju/roadmap#heading--juju-3-0-0---22-oct-2022) for the comprehensive list of changes.

The response is to therefore substitute the documented command with the equivalent 2.9.x command. For example:

### Juju 3.x:
```shell
juju integrate mysql:database mysql-test-app

juju run mysql/leader get-password 
```
### Juju 2.9.x:
```shell
juju relate mysql:database mysql-test-app

juju run-action --wait mysql/leader get-password
```
[note]
This section is based on the [OpenStack guide.](https://docs.openstack.org/charm-guide/latest/project/support-notes.html#breaking-changes-between-juju-2-9-x-and-3-x)
[/note]

<a href="#heading--upgrades"><h2 id="heading--upgrades"> Juju  upgrades </h2></a>
Newly released charm revisions might require a new [Juju version](/t/11421). This is usually because the new revision requires new Juju features, e.g. [Juju secrets](https://juju.is/docs/juju/secret).

Information about Juju requirements will be clearly indicated in the charm's [release notes](/t/11878) and in the repository's [metadata.yaml](https://github.com/canonical/mysql-operator/blob/14c06ff88c4e564cd6d098aa213bd03e78e84b52/metadata.yaml#L72-L80) file.

When upgrading your database charm with <code>juju refresh</code>, Juju checks that its version is compatible with the target revision. If not, it stops the upgrade and prevents further changes to keep the installation safe. 

```shell
~$ juju refresh mysql

Added charm-hub charm "mysql", revision 42 in channel 8.0/stable, to the model
ERROR Charm feature requirements cannot be met:
    - charm requires all of the following:
      - charm requires feature "juju" (version >= 3.1.5) but model currently supports version 3.1.4
```

You must then [upgrade to the required Juju version](/t/14325) before proceeding with the charm upgrade.