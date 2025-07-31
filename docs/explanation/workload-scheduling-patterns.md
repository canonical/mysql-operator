
# Workload scheduling patterns

This guide discusses Kubernetes (K8s) scheduling patterns for Charmed Kubeflow (CKF)  workloads.

Scheduling CKF workloads into [Pods](https://kubernetes.io/docs/concepts/workloads/pods/) to run on [K8s nodes](https://kubernetes.io/docs/concepts/architecture/nodes/) with specialised hardware requires specific configurations. These vary depending on the use case and the working environment.

The most common scheduling patterns are the following:

1. Schedule on GPU nodes.
2. Schedule on a specific node pool.
3. Schedule on [Tainted](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/) nodes.
## Schedule on GPU nodes

In most production scenarios, Pods are scheduled on GPUs using one or a combination of the following methods:

1. Setting up GPUs via their [resources](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/#using-device-plugins).
2. Configuring Taints for getting scheduled on Tainted GPU nodes.
3. Configuring [Affinities](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#node-affinity) for getting scheduled on nodes with specialised hardware.

See [Use NVIDIA GPUs](/how-to/use/use-nvidia-gpus) for more details on how to leverage NVIDIA GPU resources in your CKF deployment.

## Schedule on a specific node pool

Configuring  resources in the workload Pod allows Kubernetes to schedule it on a node with the required hardware. However, there may be additional scheduling requirements beyond hardware needs.

For example, a workload might require GPU resources but also run on a development node, not production, within a specific availability zone or data center.

This is achieved by configuring the underlying workload Pod’s [`nodeSelector`](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#nodeselector) or [`node Affinities`](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#node-affinity), specifying the list of nodes the Pod should be scheduled on.

## Schedule on Tainted nodes

Nodes with specialized hardware, such as GPUs, are very expensive. As a result, a common pattern is to use autoscaling node pools for these nodes, so they are scaled down when not in use.

To support this setup, administrators often apply Taints to these nodes, ensuring that only Pods configured with the appropriate Tolerations can be scheduled on them. See [K8s use cases](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/#example-use-cases) for more details.

In this scenario, CKF workload Pods must also be configured with the necessary Tolerations to be scheduled on the specialised nodes.

## See also
Learn how to [configure advanced scheduling](/how-to/use/configure-advanced-scheduling) for specific use cases.

-------------------------

