
# Charmed vs. upstream

This guide provides an overview about the differences between Charmed Kubeflow (CKF) and upstream [Kubeflow](https://kubeflow.org/).

Kubeflow is a collection of loosely-coupled Kubernetes components. Their deployment, maintenance and customisation requires both knowledge and effort. CKF is packaged as a set of charms, running on top of [Juju](https://juju.is/), and working as a wrapper of Kubeflow. Thanks to this abstraction, CKF simplifies Kubeflow administration and required knowledge.

While CKF is less complex than Kubeflow, it is less configurable. However, the configuration level in CKF and its default settings cover the vast majority of real-world use cases. 

## User maintenance

User maintenance is simplified in CKF.

In upstream Kubeflow, updating the default user credentials involves a number of steps, such as creating a hash of the user password and editing the [Dex config map](https://github.com/kubeflow/manifests/blob/abc72bea09259eeea96646d0414a14539e18d02a/common/dex/base/config-map.yaml#L21C1-L26C31) among others.

In CKF, `juju config` provides a simpler interface for updating the default user credentials. The Dex charm provides two [configurations](https://charmhub.io/dex-auth/configure): `static-username` and `static-password` and the [charm code](https://github.com/canonical/dex-auth-operator/blob/track/2.31/src/charm.py#L218-L231) handles the complexity of applying the change to the underlying Kubernetes cluster.

Updating the username and password is as simple as setting these two options:

```bash
juju config dex-auth static-username=user
juju config dex-auth static-password=password
```

Therefore, configuring the default username and password is simpler in CKF. However, CKF is restricted to only allow a single static user. 

## Security and stability

Charmed Kubeflow benefits from the following:

 - Upgrade guides.
 - Automated security scanning: the bundle is scanned periodically.
 - Security patching: CKF follows Canonical’s process and procedure for security patching. Vulnerabilities are prioritised based on severity, the presence of patches in the upstream project, and the risk of exploitation.
 - Comprehensive testing: CKF is thoroughly tested on multiple platforms, including public cloud, local workstations, on-premises deployments, and various CNCF-compliant Kubernetes distributions.

## Integration

Charmed Kubeflow provides integration capabilities, including:

 - Customised Prometheus exporter metrics.
 - Customised Kubeflow dashboard for Grafana.
 - Seamless integration with the Canonical Observability Stack (COS).
 - Integration with Charmed MLflow: including the ability use the MLflow registry directly from Kubeflow pipelines and notebooks.

## Enterprise offering

Charmed Kubeflow is an enterprise offering from Canonical including:

 - 24/7 support for deployment, up-time monitoring, and security patching with Charmed Kubeflow.
 - Hardening features and compliance with standards like Federal Risk and Authorisation Management Program, Health Insurance Portability and Accountability Act, and Payment Card Industry Digital Signature Standard, making it suitable for enterprises running AI/ML workloads in highly regulated environments.
 - Timely patches for common vulnerabilities and exposures (CVEs).
 - A ten-year security maintenance commitment.
 - Hybrid cloud and multi-cloud support.
 - Bug fixing.
 - Optionally managed services, allowing your team to focus on development rather than operations.
 - Consultancy services to assess the best tools and architecture for your specific use cases.
 - A simple per-node subscription model.

For enterprise enquiries, please [get in touch](https://ubuntu.com/ai#get-in-touch).

