
# Grafana dashboards

This guide presents the [Grafana](https://grafana.com) dashboards provided by Charmed Kubeflow (CKF). See [Grafana dashboards](https://grafana.com/docs/grafana/latest/dashboards/) for more details.

```{note}
All Grafana dashboards provided by CKF use the `ckf` tag.
```

## Generic dashboards

### CKF charms state

This dashboard shows the state, `up` represented in green or `down` represented in red, of CKF charms. This includes only charms that provide metrics. See [Prometheus metrics](https://charmed-kubeflow.io/docs/prometheus-metrics) to learn which are those.

![ckf-generic-dashboard|767x433](https://assets.ubuntu.com/v1/6a05687d-ckf-gen-dashboard.png)

### Istio control plane

This dashboard provides a general overview of the health and performance of the [Istio control plane](https://istio.io/). It combines metrics from `istio-pilot` and `istio-gateway`.

See [Visualizing Istio metrics with Grafana](https://istio.io/latest/docs/tasks/observability/metrics/using-istio-dashboard/) for more details.

![istio-control-plane|490x433](https://assets.ubuntu.com/v1/eb664b29-istio-control-plane.png)

## Pipelines

The following dashboards provide visualisations related to [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/) (KFP).

### ArgoWorkflow metrics

The metrics from the [`Argo Workflow`](https://argoproj.github.io/workflows/) controller expose the status of Argo Workflow [custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/), including the following information:

1. The number of workflows that have failed or are in `error` state.
1. The time workflows spend in the queue before being run.
1. The total size of captured logs that are pushed into S3 from the workflow pods.

![argo-controller-dashboard-1|690x563](upload://83LvCrng8iAn6OYc1dCrgmt9bax.png)

![argo-controller-dashboard-2|690x525](upload://ocfsL9o6oSDuBWszslRkFlf9H3W.png)

![argo-controller-dashboard-3|690x503](upload://h5AyJpspFVuPXFiwU66epsJ6yHR.png)

### Envoy service

The metrics from the `envoy` proxy expose the history of requests proxied from the KFP user interface to the [MLMD](https://www.kubeflow.org/docs/components/pipelines/concepts/metadata/) application, including the following information:

1. The total number of requests.
1. The success rate of requests with status code `non 5xx` as well the number of requests with `4xx response`, either upstream or downstream.

![envoy-dashboard|690x486](upload://lbow9tK7liiRkiIhe4dDiVqcniQ.png)

![envoy-dashboard|690x349](upload://fZYOVGehpPyhlCvDiDaWSfb2Hns.png)

### MinIO dashboard

The metrics from `MinIO` expose the status of the S3 storage instance used by KFP, including the following information:

1. S3 available space and storage capacity.
1. S3 traffic.
1. S3 API request errors and data transferred.
1. Node CPU, memory, file descriptors and IO usage.

![minio-dashboard-1|690x686](upload://m1jKpKgpY9oxDbZiwNY47CPdYt5.png)

![minio-dashboard-2|690x475](upload://1ZRzXXHlOt9tdq5DoXxe6AlnYly.png)

![minio-dashboard-3|690x634](upload://ftoDyitcNzEWS2oCEbeSGb5gIzz.png)

## Notebooks

The following dashboards provide visualisations related to [Kubeflow Notebooks](https://www.kubeflow.org/docs/components/notebooks/).

### Jupyter Notebook controller

The metrics from the `Jupyter` controller expose the status of Jupyter Notebook [custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/).

![jupyter-controller-dashboard|690x572](upload://rfJ2nSZNsoQpCyj2ge3TRT7FkT4.png)

## Experiments

The following dashboards provide visualisations related to [Katib](https://www.kubeflow.org/docs/components/katib/) experiments.

### Katib status

The metrics from the `Katib` controller expose the status of Experiment and Trial [custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/).

![katib-controller-dashboard|690x572](upload://yoY32ocEMDdCkr13EHEncOmsRbk.png)

## Serving models

The following dashboards provide visualisations related to serving ML models.

### Seldon Core

The metrics from the `Seldon Core` controller expose the status of Seldon Deployment [custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/), also called models, including information related to Seldon deployments currently available on the controller.

![seldon-controller-manager-dashboard|690x367](upload://knnnGaGnFaKHFja1K1s8Sk0HBiH.png)

