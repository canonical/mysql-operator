# Security hardening guide

This document provides an overview of security features and guidance for hardening the security of [Charmed MySQL](https://charmhub.io/mysql) deployments, including setting up and managing a secure environment.

## Environment

The environment where Charmed MySQL operates can be divided into two components:

1. Cloud
2. Juju

### Cloud

Charmed MySQL can be deployed on top of several clouds and virtualisation layers:

| Cloud              | Security guides                                                                                                                                                                                                                                                                                                                                   |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| OpenStack | [OpenStack Security Guide](https://docs.openstack.org/security-guide/)                                                                                                                                                                                                                                                                    |
| AWS           | [Best Practices for Security, Identity and Compliance](https://aws.amazon.com/architecture/security-identity-compliance), [AWS security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/security-creds.html#access-keys-and-secret-access-keys) | 
| Azure              | [Azure security best practices and patterns](https://learn.microsoft.com/en-us/azure/security/fundamentals/best-practices-and-patterns), [Managed identities for Azure resource](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/)                                                     |
| GCP         |  [Google security overview](https://cloud.google.com/kubernetes-engine/docs/concepts/security-overview), [Harden your cluster's security](https://cloud.google.com/kubernetes-engine/docs/concepts/security-overview)                                                    |

### Juju 

Juju is the component responsible for orchestrating the entire lifecycle, from deployment to Day 2 operations. For more information on Juju security hardening, see the
[Juju security page](/t/juju-security/15684) and the [How to harden your deployment](https://juju.is/docs/juju/harden-your-deployment) guide.

#### Cloud credentials

When configuring cloud credentials to be used with Juju, ensure that users have the correct permissions to operate at the required level. Juju superusers responsible for bootstrapping and managing controllers require elevated permissions to manage several kinds of resources, such as virtual machines, networks, storages, etc. Please refer to the links below for more information on the policies required to be used depending on the cloud. 

| Cloud              | Cloud user policies                                                                                                                                                                                                                                                                                                                                  |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| OpenStack | [OpenStack cloud and Juju](https://canonical-juju.readthedocs-hosted.com/en/latest/user/reference/cloud/list-of-supported-clouds/the-openstack-cloud-and-juju/)                                                                                                                                                                                                                                                                    |
| AWS           | [Juju AWS Permission](https://discourse.charmhub.io/t/juju-aws-permissions/5307), [AWS Instance Profiles](https://discourse.charmhub.io/t/using-aws-instance-profiles-with-juju-2-9/5185), [Juju on AWS](https://juju.is/docs/juju/amazon-ec2)| 
| Azure              | [Juju Azure Permission](https://juju.is/docs/juju/microsoft-azure), [How to use Juju with Microsoft Azure](https://discourse.charmhub.io/t/how-to-use-juju-with-microsoft-azure/15219)                                                    |
| GCP         |  [Google GCE cloud and Juju](https://canonical-juju.readthedocs-hosted.com/en/latest/user/reference/cloud/list-of-supported-clouds/the-google-gce-cloud-and-juju/)                                               |

#### Juju users

It is very important that Juju users are set up with minimal permissions depending on the scope of their operations. Please refer to the [User access levels](https://juju.is/docs/juju/user-permissions) documentation for more information on the access levels and corresponding abilities.

Juju user credentials must be stored securely and rotated regularly to limit the chances of unauthorized access due to credentials leakage.

## Applications

In the following, we provide guidance on how to harden your deployment using:

1. Operating system
2. Security upgrades
3. Encryption 
4. Authentication
5. Monitoring and auditing

### Operating system

Charmed MySQL and Charmed MySQL Router run on top of Ubuntu 22.04. Deploy a [Landscape Client Charm](https://charmhub.io/landscape-client?) to connect the underlying VM to a Landscape User Account to manage security upgrades and integrate [Ubuntu Pro](https://ubuntu.com/pro) subscriptions. 

### Security upgrades

Charmed MySQL operator and Charmed MySQL Router operator install a pinned revision of the Charmed MySQL snap to provide reproducible and secure environments.

New versions (revisions) of charmed operators can be released to upgrade workloads, the operator's code, or both. It is important to refresh the charm regularly to make sure the workload is as secure as possible.

For more information on upgrading the charm, see the [How to upgrade MySQL](https://canonical.com/data/docs/mysql/iaas/h-upgrade) and [How to upgrade MySQL Router](https://charmhub.io/mysql-router/docs/h-upgrade-intro?channel=dpe/edge) guides, as well as the [Release notes](https://canonical.com/data/docs/mysql/iaas/r-releases).

### Encryption

By default, encryption is optional for both external connections and internal communication between cluster members. To enforce encryption in transit, integrate Charmed MySQL with a TLS certificate provider. Please refer to the [Charming Security page](https://charmhub.io/topics/security-with-x-509-certificates) for more information on how to select the right certificate provider for your use case.

Encryption in transit for backups is provided by the storage (Charmed MySQL is a client for the S3 storage).

For more information on encryption, see the [Cryptography](https://discourse.charmhub.io/t/charmed-mysql-explanations-cryptography/16785) explanation page and [How to enable encryption](https://canonical.com/data/docs/mysql/iaas/h-enable-tls) guide.

### Authentication

Charmed MySQL uses the [caching_sha2_password](https://dev.mysql.com/doc/refman/8.0/en/caching-sha2-pluggable-authentication.html) plugin for authentication. 

### Monitoring and auditing

Charmed MySQL provides native integration with the [Canonical Observability Stack (COS)](https://charmhub.io/topics/canonical-observability-stack). To reduce the blast radius of infrastructure disruptions, the general recommendation is to deploy COS and the observed application into separate environments, isolated from one another. Refer to the [COS production deployments best practices](https://charmhub.io/topics/canonical-observability-stack/reference/best-practices) for more information.

For instructions, see the [How to enable monitoring](https://canonical.com/data/docs/mysql/iaas/h-enable-monitoring), [How to enable alert rules](https://canonical.com/data/docs/mysql/iaas/h-enable-alert-rules), and [How to enable tracing](https://canonical.com/data/docs/mysql/iaas/h-enable-tracing) guides.

The Audit log plugin is enabled by default and produces login/logout logs. See the [Audit Logs](https://charmhub.io/mysql/docs/e-audit-logs) guide for further configuration. These logs are stored in the `/var/snap/charmed-mysql/common/var/log/mysql` directory of the MySQL container and are rotated every minute to the `/var/snap/charmed-mysql/common/var/log/mysql/archive_audit` directory. It’s recommended to integrate the charm with [COS](https://discourse.charmhub.io/t/9900), from where the logs can be easily persisted and queried using [Loki](https://charmhub.io/loki-k8s)/[Grafana](https://charmhub.io/grafana).

## Additional Resources

For details on the cryptography used by Charmed MySQL, see the [Cryptography](https://discourse.charmhub.io/t/charmed-mysql-explanations-cryptography/16785) explanation page.