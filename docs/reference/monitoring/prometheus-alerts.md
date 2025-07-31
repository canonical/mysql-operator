
# Prometheus alerts

This guide presents an overview of the Charmed Kubeflow (CKF) charms that provide alert rules to facilitate their monitoring.

All alerts can be accessed using the Prometheus or Grafana User Interface (UI). See [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) for more information.

```{note}
The tables below provide the following information:

* Alert: alert name within the Prometheus dashboard.
* Description: when the alert is triggered. See [Grafana alerting](https://grafana.com/docs/grafana/latest/alerting/fundamentals/) for more details.
* Severity: alert severity, where common values are “Warning” or “Critical”.
```

## Argo controller

Alert | Description | Severity
--- | --- | ---
ArgoWorkflowWarningLoglines | The argo-controller warning logs have increased by at least 40 lines per minute for the last four minutes. | Warning
ArgoWorkflowErrorLoglines | The argo-controller warning logs have increased by at least 10 lines per minute for the last four minutes. | Critical
ArgoWorkflowsFailed | Amount of failing Argo Workflows is increasing. | Warning
ArgoWorkflowsErroring | Amount of erroring Argo Workflows is increasing. | Warning
ArgoWorkflowsPending | Amount of pending Argo Workflows is increasing. | Warning
KubeflowServiceDown | Argo-controller service is down. | Critical
KubeflowServiceIsNotStable | Argo-controller service is not stable. | Warning

## Dex Auth

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Dex-auth service is down. | Critical
KubeflowServiceIsNotStable | Dex-auth service is not stable. | Warning

## Envoy

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Envoy service is down. | Critical
KubeflowServiceIsNotStable | Envoy service is not stable. | Warning

## Istio gateway

Alert | Description | Severity
--- | --- | ---
HTTP5xxRateHigh | 5xx rate too high. | Critical
WorkloadLatencyP99High | The workload request latency P99 > 160ms.  | Warning
IngressLatencyP99High | The ingress latency P99 > 250ms.  | Warning
IngressTrafficMissing | Ingress gateway traffic missing. | Critical
IstioMetricsMissing | Istio Metrics missing. | Critical
KubeflowServiceDown | Istio-gateway service is down. | Critical
KubeflowServiceIsNotStable | Istio-gateway service is not stable. | Warning

## Istio pilot

Alert | Description | Severity
--- | --- | ---
IstioPilotAvailabilityDrop | Istio-pilot availability drops. | Critical
KubeflowServiceDown | Istio-gateway service is down. | Critical
KubeflowServiceIsNotStable | Istio-gateway service is not stable. | Warning

## Jupyter controller

Alert | Description | Severity
--- | --- | ---
JupyterControllerRuntimeReconciliationErrorsExceedThreshold | Total number of reconciliation errors per controller. | Critical
UnfinishedWorkQueueAlert | Increase in unfinished work in the work queue. | Critical
KubeflowServiceDown | Jupyter-controller service is down. | Critical
KubeflowServiceIsNotStable | Jupyter-controller service is not stable. | Warning
FileDescriptorsExhausted | File descriptors at 98% of maximum. | Critical
FileDescriptorsSoonToBeExhausted | File descriptors expected to reach maximum in one hour. | Warning

## Katib controller

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Katib-controller service is down. | Critical
KubeflowServiceIsNotStable | Katib-controller service is not stable. | Warning

## KFP api

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Kfp-api service is down. | Critical
KubeflowServiceIsNotStable | Kfp-api service is not stable. | Warning

## Knative operator

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Knative-operator service is down. | Critical
KubeflowServiceIsNotStable | Knative-operator service is not stable. | Warning

## Kserve controller

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Kserve-controller service is down. | Critical
KubeflowServiceIsNotStable | Kserve-controller service is not stable. | Warning

## Kubeflow profiles

Alert | Description | Severity
--- | --- | ---
KfamDown | Kubeflow-kfam service is down. | Critical
ProfilesDown | Kubeflow-profiles service is down. | Critical
KubeflowServiceDown | Kubeflow-profiles service is down. | Critical
KubeflowServiceIsNotStable | Kubeflow-profiles service is not stable. | Warning

## Metacontroller operator

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Metacontroller-operator service is down. | Critical
KubeflowServiceIsNotStable | Metacontroller-operator service is not stable. | Warning

## MinIO

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | MinIO service is down. | Critical
KubeflowServiceIsNotStable | MinIO service is not stable. | Warning

## MLflow server

Alert | Description | Severity
--- | --- | ---
MLFlowRequestDurationTooLong | MLflow-server requests taking longer than expected. | Critical
KubeflowServiceDown | MLflow-server service is down. | Critical
KubeflowServiceIsNotStable | MLflow-server service is not stable. | Warning

## Pvcviewer operator

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Pvcviewer-operator service is down. | Critical
KubeflowServiceIsNotStable | Pvcviewer-operator service is not stable. | Warning

## Seldon controller manager

Alert | Description | Severity
--- | --- | ---
SeldonWorkqueueTooManyRetries | Seldon workqueue retries increasing for `kubeflow/seldon-core/0`. | Critical
SeldonHTTPError | Seldon HTTP error in `kubeflow/seldon-core/0`. | Critical
SeldonReconcileError | Seldon reconciliation `kubeflow/seldon-core/0` failed. | Critical
SeldonUnfinishedWorkIncrease | Seldon unfinished work for `kubeflow/seldon-core/0` is increasing. | Critical
SeldonWebhookError | Seldon webhook failed for `kubeflow/seldon-core/0`. | Critical
KubeflowServiceDown | Seldon-core service is down. | Critical
KubeflowServiceIsNotStable | Seldon-core service is not stable. | Warning

## Tensorboard-controller

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Tensorboard-controller service is down. | Critical
KubeflowServiceIsNotStable | Tensorboard-controller service is not stable. | Warning

## Training operator

Alert | Description | Severity
--- | --- | ---
KubeflowServiceDown | Training-operator service is down. | Critical
KubeflowServiceIsNotStable | Training-operator service is not stable. | Warning

-------------------------

