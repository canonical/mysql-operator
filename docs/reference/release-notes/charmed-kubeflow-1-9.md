
# Charmed Kubeflow 1.9

```{note}
Release date: July 31st, 2024
```

## What’s new

* Support for Kubernetes from version 1.26 to 1.29.
* [Support for Juju 3.4](https://discourse.charmhub.io/t/charmed-kubeflow-support-for-juju-3/14734) (previously 3.1).
* Pipelines upgraded to version 2.2.0 (previously 2.0.3).[ #483](https://github.com/canonical/kfp-operators/pull/483)
* KServe upgraded to version 0.13 (previously 0.11).[ #239](https://github.com/canonical/kserve-operators/pull/239)
* Istio upgraded to version 1.22 (previously 1.17).
* Knative upgraded to version 1.12 (previously 1.10).[ #182](https://github.com/canonical/knative-operators/pull/182)
* [Integration with Nvidia NGC containers](https://charmed-kubeflow.io/docs/launch-ngc-notebooks) via the[ ngc-integrator-operator](https://github.com/canonical/ngc-integrator-operator) charm.
* [Integration with Triton](https://charmed-kubeflow.io/docs/serve-a-model-using-triton-inference-server) Inference Server for KServe.[ #171](https://github.com/canonical/knative-operators/issues/171)
* Charms state grafana dashboard [#877](https://github.com/canonical/bundle-kubeflow/issues/877)
* [Enabled Istio CNI plugin](https://charmed-kubeflow.io/docs/enable-istio-cni-plugin).[ #365](https://github.com/canonical/istio-operators/pull/365)
* Reworked the [way Charmed Kubeflow](https://charmed-kubeflow.io/docs/monitoring) is monitored with the Canonical Observability stack.
* Added ROCKs for following charms [#94](https://github.com/canonical/pipelines-rocks/issues/94), [#95](https://github.com/canonical/pipelines-rocks/issues/95), [#96](https://github.com/canonical/pipelines-rocks/issues/96), [#97](https://github.com/canonical/pipelines-rocks/issues/97), [#98](https://github.com/canonical/pipelines-rocks/issues/98), [#99](https://github.com/canonical/pipelines-rocks/issues/99), [#23](https://github.com/canonical/argo-workflows-rocks/issues/23), [#14](https://github.com/canonical/dex-auth-rocks/issues/14), [#67](https://github.com/canonical/kserve-rocks/issues/67), [#68](https://github.com/canonical/kserve-rocks/issues/68), [#69](https://github.com/canonical/kserve-rocks/issues/69), [#70](https://github.com/canonical/kserve-rocks/issues/70), [#71](https://github.com/canonical/kserve-rocks/issues/71), [#72](https://github.com/canonical/kserve-rocks/issues/72) [#73](https://github.com/canonical/kserve-rocks/issues/73), [#74](https://github.com/canonical/kserve-rocks/issues/74), [#99](https://github.com/canonical/kubeflow-rocks/issues/99), [#98](https://github.com/canonical/kubeflow-rocks/issues/98).

## Bug fixes

* Fixed non-working grafana dashboards for some charms (minio, notebooks, envoy, katib, argo). [#856](https://github.com/canonical/bundle-kubeflow/issues/856)
* Fixed katib-ui charm trying to access the workload container by the wrong name.[ #156](https://github.com/canonical/katib-operators/issues/156)
* Introduced k8s-service-info relation between katib-controller and katib-db-manager.[ #185](https://github.com/canonical/katib-operators/pull/185)
* Refactored the kserve-controller charm to use an all-catch main event handler.[ #197](https://github.com/canonical/kserve-operators/pull/197)
* Introduced handling of relation-broken events in kfp-api.[ #272](https://github.com/canonical/kfp-operators/pull/272)
* Patched KFP Profile Controller service port.[ #318](https://github.com/canonical/kfp-operators/pull/318)
* Set explicitly the command for kfp-schedwf pebble layer.[ #347](https://github.com/canonical/kfp-operators/pull/347)
* Fixed `self._cni_config_changed` call and handled exceptions in istio-pilot.[ #396](https://github.com/canonical/istio-operators/pull/396)
* Corrected null values for configurations in spawner_ui_config.yaml for jupyter-ui.[ #361](https://github.com/canonical/notebook-operators/pull/361)

## Enhancements

* Istio ingress can be configured with TLS using either a TLS certificate provider or by passing the TLS key and cert directly to the `istio-pilot` charm as a Juju seceret. Refer to [Enable TLS ingress gateway for a single host](https://charmed-kubeflow.io/docs/enable-tls-ingress-gateway-for-a-single-host) for more information.
* Set `meshConfig.accessLogFile` configuration for exposing logs in istio-pilot.[ #371](https://github.com/canonical/istio-operators/pull/371)
* Added `csr-domain-name` config option for istio-pilot.[ #381](https://github.com/canonical/istio-operators/pull/381)
* Added config for queue sidecar image to knative-serving charm.[ #186](https://github.com/canonical/knative-operators/pull/186)
* Added [configuration support for Kubeflow notebooks page](https://charmed-kubeflow.io/docs/configure-the-kubeflow-notebook-creation-page) in the UI. [#345](https://github.com/canonical/notebook-operators/pull/345)
* Added `cluster-domain`, `cull-idle-time` and `idleness-check-period` config options to notebook-operator. [#372](https://github.com/canonical/notebook-operators/pull/372)
* Removed the need for `public-url` configuration for `dex-auth` and `oidc-gatekeeper`, and at the same time allow better integration with Dex connectors  by allowing the configuration of the Dex issuer URL [#209](https://github.com/canonical/dex-auth-operator/pull/209) and [#163](https://github.com/canonical/oidc-gatekeeper-operator/pull/163).


## Deprecated

* Removed `seldon-core` from the bundle definition. This does not affect the deployment upgrade from version 1.8.

-------------------------

