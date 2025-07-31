
# Charmed Kubeflow 1.10

```{note}  
Release date: April 7th, 2025  
```

This page contains the release notes for Charmed Kubeflow (CKF) 1.10. 

See [Kubeflow 1.10.0](https://github.com/kubeflow/manifests/releases/tag/v1.10.0)  for details on the upstream Kubeflow release notes. In comparison with the upstream Kubeflow project, CKF:

* Uses [OIDC-Authservice](https://github.com/arrikto/oidc-authservice) for authentication.  
* Does not include the [Model registry](https://github.com/kubeflow/model-registry) and [Spark operator](https://github.com/kubeflow/spark-operator) components.

## What’s new

### Highlights

* Implemented automatic [profiles](https://www.kubeflow.org/docs/components/central-dash/profiles/#what-is-a-kubeflow-profile) management using the new [GitHub Profiles Automator](https://charmhub.io/github-profiles-automator) charm. This is an optional feature. See [Manage profiles](https://charmed-kubeflow.io/docs/manage-profiles) for more information.  
* Enabled the configuration of High Availability for Istio gateway ([\#553](https://github.com/canonical/istio-operators/pull/553)).  
* Improved application-health monitoring by exposing new metrics and providing new alert rules and Grafana dashboards for KServe, Istio and various other components. 

### Upgrades

* Argo upgraded to 3.4.17 (previously 3.4.16).  
* Dex upgraded to 2.41.1 (previously 2.39.1).  
* Istio upgraded to 1.24 (previously 1.22).  
* Knative upgraded to 1.16.0 (previously 1.12).  
* KServe upgraded to 0.14.1 (previously 0.13.0).  
* Metacontroller upgraded to 4.11.22 (previously 3.0).  
* Pipelines upgraded to 2.4.1 (previously 2.3.0).  
* Training-operator upgraded to 1.9 (previously 1.8).  
* Support for Kubernetes 1.29-1.31.  
* Support for Juju 3.6.

### Features

* Enhanced security by integrating the following [rocks](https://documentation.ubuntu.com/server/explanation/virtualisation/about-rock-images/index.html):  
  * Pipelines ([\#158](https://github.com/canonical/pipelines-rocks/pull/158), [\#159](https://github.com/canonical/pipelines-rocks/pull/159), [\#160](https://github.com/canonical/pipelines-rocks/pull/160), [\#3](https://github.com/canonical/envoy-rock/pull/3)).  
  * Kubeflow ([\#87](https://github.com/canonical/kubeflow-rocks/pull/87), [\#114](https://github.com/canonical/kubeflow-rocks/pull/114), [\#154](https://github.com/canonical/kubeflow-rocks/pull/154)).  
  * Knative ([\#4](https://github.com/canonical/knative-rocks/pull/4), [\#5](https://github.com/canonical/knative-rocks/pull/5), [\#6](https://github.com/canonical/knative-rocks/pull/6), [\#10](https://github.com/canonical/knative-rocks/pull/10), [\#18](https://github.com/canonical/knative-rocks/pull/18)).  
  * Training-operator ([\#2](https://github.com/canonical/training-operator-rock/pull/2)).  
  * KServe ([\#102](https://github.com/canonical/kserve-rocks/pull/102), [\#103](https://github.com/canonical/kserve-rocks/pull/103), [\#104](https://github.com/canonical/kserve-rocks/pull/104), [\#106](https://github.com/canonical/kserve-rocks/pull/106)).  
* Enhanced observability by:  
  * Enabling metrics for:  
    * `knative-operator` ([\#212](https://github.com/canonical/knative-operators/pull/212)).   
    * `kserve-controller` ([\#261](https://github.com/canonical/kserve-operators/pull/261)).  
  * Enabling metrics and adding alert rules to:  
    * `istio-gateway` ([\#477](https://github.com/canonical/istio-operators/pull/477), [\#514](https://github.com/canonical/istio-operators/pull/514)).  
    * `tensorboard-controller` ([\#130](https://github.com/canonical/kubeflow-tensorboards-operator/pull/130)).  
    * `kubeflow-profiles` ([\#181](https://github.com/canonical/kubeflow-profiles-operator/pull/181)).  
  * Enabling metrics and adding alert rules and Grafana dashboard to `kubeflow-dashboard` ([\#254](https://github.com/canonical/kubeflow-dashboard-operator/pull/254)).  
  * Adding basic alert rules regarding the charm’s health to:  
    * `argo-controller` ([\#195](https://github.com/canonical/argo-operators/pull/195)).  
    * `dex-auth` ([\#225](https://github.com/canonical/dex-auth-operator/pull/225)).  
    * `envoy` ([\#130](https://github.com/canonical/envoy-operator/pull/130)).  
    * `istio-pilot` ([\#515](https://github.com/canonical/istio-operators/pull/515)).  
    * `katib-controller` ([\#231](https://github.com/canonical/katib-operators/pull/231)).  
    * `knative-operator` ([\#215](https://github.com/canonical/knative-operators/pull/215)).  
    * `kserve-controller` ([\#265](https://github.com/canonical/kserve-operators/pull/265)).  
    * `metacontroller-operator` ([\#124](https://github.com/canonical/metacontroller-operator/pull/124)).  
    * `minio` ([\#184](https://github.com/canonical/minio-operator/pull/184)).  
    * `jupyter-controller` ([\#402](https://github.com/canonical/notebook-operators/pull/402)).  
    * `pvcviewer-operator` ([\#55](https://github.com/canonical/pvcviewer-operator/pull/55)).  
    * `training-operator` ([\#191](https://github.com/canonical/training-operator/pull/191)).  
  * Adding alert rules and an Istio control plane dashboard to `istio-pilot` ([\#478](https://github.com/canonical/istio-operators/pull/478)).

## Bug fixes

* Enabled the configuration of proxy environment variables in `knative-serving` controller ([\#208](https://github.com/canonical/knative-operators/pull/208)).  
* Refactored `knative-{eventing,serving}` charms to block if the Knative [CRDs](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/#customresourcedefinitions) are not found ([\#276](https://github.com/canonical/knative-operators/pull/276), [\#281](https://github.com/canonical/knative-operators/pull/281)).  
* Refactored `knative-{eventing,serving}` charms to use a JSON file for handling custom images ([\#304](https://github.com/canonical/knative-operators/pull/304)).  
* Enabled the configuration of proxy environment variables in the `storage-initializer` initContainer of `kserve-controller` ([\#257](https://github.com/canonical/kserve-operators/pull/257)).  
* Removed unused [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) proxy layer from `kserve-controller` ([\#289](https://github.com/canonical/kserve-operators/pull/289)).  
* Added missing `ClusterServingRuntime` validation webhook ([\#314](https://github.com/canonical/kserve-operators/pull/314)).  
* Added a namespace field to the ingress relation data in `kubeflow-dashboard` to fix cross-model ingresses ([\#176](https://github.com/canonical/kubeflow-dashboard-operator/pull/176)).  
* Fixed the metrics collector for `metacontroller-operator` ([\#101](https://github.com/canonical/metacontroller-operator/pull/101)).  
* Decreased the discovery interval of `metacontroller-operator` to update cached resources more quickly ([\#117](https://github.com/canonical/metacontroller-operator/pull/117)).  
* Added missing [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) rules to `metacontroller-operator` ([\#158](https://github.com/canonical/metacontroller-operator/pull/158)).  
* Set charm status to `blocked` when `secret-key` is too short in `minio` ([\#178](https://github.com/canonical/minio-operator/pull/178)).  
* Removed an alert rule in `jupyter-controller` that was constantly firing due to an upstream bug ([\#412](https://github.com/canonical/notebook-operators/pull/412)).  
* Used the same service name for its rock and charm for `kfp-metadata-writer` ([\#167](https://github.com/canonical/pipelines-rocks/pull/167)).

## Deprecated

* The use of Kubeflow Pipelines SDK v1 is deprecated. Please migrate your existing v1 pipelines to v2 following the [migration instructions](https://www.kubeflow.org/docs/components/pipelines/user-guides/migration/). SDK v1 can still be used but Canonical does not provide support, patches or fixes related to its use.  
* Removed `create-profile` and `initialise-profile` actions from `kubeflow-profiles` [\#210](https://github.com/canonical/kubeflow-profiles-operator/pull/210). For managing profiles in CKF 1.10, see [Manage profiles](https://charmed-kubeflow.io/docs/manage-profiles).

