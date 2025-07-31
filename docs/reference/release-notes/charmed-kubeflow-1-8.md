
# Charmed Kubeflow 1.8

```{note}
Release date: Nov 22nd, 2023
```

## What's new
* Support for Kubernetes 1.25 until 1.29
* Support for juju 3.1
* kfp-operators now point at version 2.0.3 of pipelines, previously it was 2.0.0-alpha.7 [#379](https://github.com/canonical/kfp-operators/pull/379)  
  * Please make sure to check out the [required steps](https://discourse.charmhub.io/t/kfp-charms-from-charmed-kubeflow-1-7-migrated-to-channel-2-0-alpha-7/12381) after this change.
* kfp-metadata-writer charm has been added to the kfp-operators offerings [#350](https://github.com/canonical/kfp-operators/pull/350)
* kfp-operators and katib-operators are now integrated with mysql-k8s charm [#205](https://github.com/canonical/kfp-operators/pull/205) and [#72](https://github.com/canonical/katib-operators/pull/72)
* kserve-controller defaults to `Serverless` deployment mode for integrating with the kserve-operators to provide serverless Inference Services [#178](https://github.com/canonical/kserve-operators/pull/178)
* kubeflow-dashboard has a customizable sidebar, users can now integrate new menu links in the sidebar [#130](https://github.com/canonical/kubeflow-dashboard-operator/pull/130)
* The pvcviewer-operator [charm](https://github.com/canonical/pvcviewer-operator) enable users to open a filebrowser on arbitrary persistent volume claims, letting them inspect, download, upload and manipulate data.
* The newer bundle deploys [envoy](https://github.com/canonical/envoy-operator) and [mlmd](https://github.com/canonical/mlmd-operator) as dependencies of the new pipelines backend.
* jupyter-operators now offer a way to dynamically to enable users to set their desired images in each Notebook type: Jupyter, Rstudio, and VSCode [#259](https://github.com/canonical/notebook-operators/pull/259)

For a list of all the new workload versions in our charms as well as the supported versions of dependencies and infrastructure, please refer to [#643](https://github.com/canonical/bundle-kubeflow/issues/643)

## Bug fixes
* latest/edge charm stuck in maintenance with `Workload failed health check` [#110](https://github.com/canonical/admission-webhook-operator/issues/110)
* `RBAC: access denied` on connecting to a notebook - 1.8 pre-release [#309](https://github.com/canonical/notebook-operators/issues/309)
* `istio-pilot` fails to process `ingress-relation-broken` event during charm remove [#189](https://github.com/canonical/istio-operators/issues/189)
* `kfp-api` error on relational-db-relation-broken [#222](https://github.com/canonical/kfp-operators/issues/222)
* `istio-pilot` cannot be removed by juju remove-application [#292](https://github.com/canonical/istio-operators/issues/292)

## Enhancements
* istio-pilot integration with the tls-certificates interface for TLS termination. This also allows users to use certificates provider charms to secure the connection (see [README.md](https://github.com/canonical/istio-operators/tree/main/charms/istio-pilot#enable-tls-ingress-gateway-for-a-single-host)) [#338](https://github.com/canonical/istio-operators/pull/338)
* argo-controller now uses the `emissary` executor by default [#122](https://github.com/canonical/argo-operators/pull/122)
* dex-auth has a newer charm configuration for disabling static password [#153](https://github.com/canonical/dex-auth-operator/pull/153)
* jupyter-ui backend mode change to 'production' [#271](https://github.com/canonical/notebook-operators/pull/271)

## Deprecated
* argo-server has been removed from the bundle definition
* mindspore image from Notebooks UI [#293](https://github.com/canonical/notebook-operators/pull/293)

