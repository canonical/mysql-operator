
# System architecture

This guide describes the [Charmed Kubeflow (CKF)](https://charmed-kubeflow.io/) system architecture, its components, and its integration with other products and tools.

## Minimum system requirements

CKF runs on any [Cloud Native Computing Foundation (CNCF)-compliant](https://www.cncf.io/certification/software-conformance/#logos) Kubernetes (K8s) with these minimum requirements for the underlying infrastructure:

|Resource|Dimension|
| --- | --- |
|Memory (GB)|16|
|Storage (GB)|50|
|CPU processor|4-core|

CKF also works in GPU-accelerated environments. There are no minimum requirements regarding the number of needed GPUs as this depends on the use case. Refer to the following guides for more details:

* [Install on NVIDIA DGX](https://charmed-kubeflow.io/docs/install-on-nvidia-dgx).
* [Launch NVIDIA NGC notebooks](https://charmed-kubeflow.io/docs/launch-nvidia-ngc-notebooks).

## System architecture overview

Charmed Kubeflow is a cloud-native application that integrates several components at different layers:

* At the *infrastructure* level, it can be deployed on any certified Kubernetes using from local to public clouds.
* The *service mesh* component is [Istio](https://charmhub.io/istio). It is used for traffic management and access control. 
* The *authentication* layer is built upon [Dex IdP](https://dexidp.io/) and an OIDC Client, usually `OIDC Authservice` or `oauth2 proxy`.
* The *storage and database* layer comprises MySQL and [MinIO](https://charmhub.io/minio), used as the main storage and S3 storage solutions respectively. They are commonly used for storing logs, artefacts, and workload definitions.

![arch_overview](https://assets.ubuntu.com/v1/141d8b49-arch_overview.png)

The main components of CKF can be split into:

* Control plane: responsible for the core operations of Charmed Kubeflow, such as its User Interface (UI), user and authorization management, and volume management. The control plane is comprised of:
  * Web applications: web UI components that provide a point of interaction between the user and their ML workloads.
  * Central dashboard: displays the web applications.
  * Controllers: business logic to manage different operations, such as profile or volume management.
* Applications: enable and manage different user workloads, such as training, experimentation with notebooks, ML pipelines, and model serving.
* Integrations: Charmed Kubeflow is integrated with components that may not be always enabled in upstream Kubeflow, like Knative for serverless support.

## Components

### Central dashboard and web apps

The central dashboard provides an authenticated web interface for CKF components. It acts as a hub for the components and user workloads running in the cluster. The main features of the central dashboard include:

* Authentication and authorization based on Kubeflow profiles.
* Access to user interfaces of Kubeflow components, such as Notebook servers or Katib experiments.
* Ability to customize the links for accessing external applications.

The following diagram shows the dashboard overall operation and how it interacts with web and authentication applications:

![central_dashboard](https://assets.ubuntu.com/v1/21e3cff3-dashboard.png)

From the diagram above:

* The central dashboard is the landing page that displays the web applications. It is integrated with Istio, Dex and the OIDC client to provide an authenticated web interface.
* The web applications give access to the various components of CKF. They are also integrated with Istio, Dex and the OIDC client to provide authentication.
* The web applications also take an important role in how users interact with the actual resources deployed in the Kubernetes cluster, as they are the ones executing actions, such as `create`, `delete`, `list`, based on [K8s RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### Profiles

User isolation in CKF is mainly handled by the Kubeflow profiles component. In the Kubeflow context, a *profile* is a Kubernetes Custom Resource Definition (CRD) that wraps a Kubernetes namespace to add owners and contributors.

A profile can be created by the deployment administrator via the central dashboard or by applying a Profile Custom Resource. The deployment administrator can define the owner, contributors, and resource quotas.

![profiles](https://assets.ubuntu.com/v1/e6ade25f-profiles.png)

From the diagram above:

* Kubeflow profiles is the component responsible for reconciling the Profile Custom Resources (CRs) that should exist in the Kubernetes deployment.
* Each profile has a one-to-one mapping to a namespace, which contains:
  * User (admin and contributors) workloads, such as notebooks, pipelines and training jobs.
  * `RoleBindings` so users can access resources in their namespaces.
  * `AuthorizationPolicies` for access control.
* Different actors can access different profiles depending on their role:
  * admins can access their own namespaces and the resources deployed in them. They can also modify contributors.
  * contributors have access to the namespaces they have been granted access to, but cannot modify the contributors.

### Pipelines

The pipelines component enables the development and deployment of portable and scalable ML workloads.

![pipelines](https://assets.ubuntu.com/v1/f21cceac-pipelines.png)

From the diagram above:

* The pipelines web app is the user interface for managing and tracking experiments, jobs, and runs.
* The pipelines component schedules workflows, visualization, multi-user management, and the API server that manages and reconciles the operations.
* Pipelines use Argo for workflow orchestration.
* Pipelines rely on different storage and database solutions for different purposes:
  * ML metadata store: used for storing ML metadata, the application that handles it is called `ml-metadata`.
  * Artefact store: used for storing logs and ML artifacts resulting from each pipeline run step, the application used for this is MinIO.
  * Kubeflow pipelines database: used for storing statuses, and pipeline definitions. It is usually a MySQL database.

#### Pipeline runs lifecycle

1. A request from the user is received, either via the web app or from a notebook, to create a new pipeline run.
2. The Argo controller will reconcile the argo workflows in the pipeline definition, creating the necessary Pods for running the various steps of the pipeline.
3. During the pipeline run, each step may generate logs, ML metadata, and ML artifacts, which are stored in the various storage solutions integrated with pipelines.

While the run is executing and after completion, users can see the result of the run, and access the logs and artifacts generated by the pipeline.

### AutoML

Automated Machine Learning (AutoML) allows users with minimal knowledge of ML to create ML projects leveraging different tools and methods. 

In CKF, AutoML is achieved using [Katib](https://www.kubeflow.org/docs/components/katib/overview/) for hyperparameter tuning, early stopping, and neural architecture search. The Training operator is used for executing model training jobs.

![automl](https://assets.ubuntu.com/v1/fd699aae-automl.png)

From the diagram above:

* The Katib controller is responsible for reconciling experiment CRs.
* Each experiment is comprised of:
  * Trials: an iteration of the experiment, e.g., hyperparameter tuning.
  * Workers: the actual jobs that train the model, for which the Training operator is responsible for.
* The Katib web app is the main landing page for users to access and manage experiments.
* The Katib DB manager is responsible for storing and loading the trial metrics.

### Notebooks

Kubeflow notebooks enable users to run web-based development environments. It provides support for JupyterLab, R-Studio, and Visual Studio Code.

With Kubeflow notebooks, users can create development environments directly in the Kubernetes cluster rather than locally, where they can be shared with multiple users, if allowed.

![notebooks](https://assets.ubuntu.com/v1/97795a66-notebooks.png)

From the diagram above:

* The notebooks controller is responsible for reconciling the Notebook servers that must exist.
  * Disambiguation: a notebook server is the backend that provides the core functionality for running and interacting with the development environments that are notebooks. For example, a Jupyter notebook server can hold multiple .ipynb notebooks.
* The notebooks web app is the landing page for users to manage and interact with the notebook servers.
* Each notebook server has a PersistentVolumeClaim (PVC) where the notebooks data are stored.

### KServe

#### Model server

A model server enables ML engineers to host models and make them accessible over a network. In Charmed Kubeflow, this is done using KServe.

![kserver](https://assets.ubuntu.com/v1/a22aef42-kserve.png)

From the diagram above:

* The Kserve controller reconciles the InferenceService (ISVC) CR.
* The ISVC is responsible for creating a Kubernetes Deployment with two Pods:
  * Transformer: responsible for converting inference requests into data structures that the model can understand. It also transforms back the prediction returned by the model into predictions with labels.
  * Predictor: responsible for pulling pre-trained models from a model registry, loading them, and returning predictions based on the inference requests.

#### Serverless model service

When configured in “serverless mode”, KServe leverages the serverless capabilities of Knative. In this mode, components like Istio are leveraged for traffic management.

![serverless](https://assets.ubuntu.com/v1/7c044f39-serverless.png)

From the diagram above:

* The Istio IngressGateway receives an inference request from the user and routes it to the KnativeService (KSVC) that corresponds to the InferenceService, i.e., the model server, provided this resource is exposed outside the cluster.
* The KSVC manages the workload lifecycle, in this case the ISVC. It controls the following:
  * Route: routes the requests to the corresponding revision of the workload.
  * Configurator: records history of the multiple revisions of the workload.
* The Knative serving component is responsible for reconciling the KSVCs in the Kubernetes deployment. It includes the following components:
  * Activator: queues incoming requests and communicates with the Autoscaler to bring scaled-to-zero workloads back up.
  * Autoscaler: scales up and down the workloads.

##### Inference request flow

1. The Istio IngressGateway receives the inference request and directs it to the KSVC.

    - If the ISVC is scaled down to zero, the Activator will request the Autoscaler to scale up the ISVC Pods.

2. Once the request reaches the KSVC, the Router ensures that the request is routed to the correct revision of the ISVC.
3. The ISVC receives the request at the Transformer Pod for request transformation.
4. Inference is performed at the Predictor Pod.
5. The response is then re-routed back to the user.

## Integrations

CKF integrates with various solutions of the [Juju](https://juju.is/) ecosystem.

### Charmed MLflow

CKF integrates with the [Charmed MLflow bundle](https://charmhub.io/mlflow) for experiment tracking and as a model registry.

![cmlflow](https://assets.ubuntu.com/v1/7ad21148-cmlflow.png)

From the diagram above:

* The resource dispatcher is a component that injects PodDefaults and credentials into each user Profile to be able to access the Charmed MLflow model registry.
  * PodDefaults are CRs responsible for ensuring that all Pods in a labelled namespace get mutated as desired.
* Charmed MLflow integrates with the resource dispatcher to send its credentials, server endpoint information and S3 storage information, i.e., the MinIO endpoint.
* With this integration, users can enable access to Charmed MLflow from their notebook servers to perform experiment tracking, or access the model registry.

The Charmed MLflow is also integrated with the central dashboard and served behind the Charmed Kubeflow ingress:

![ckf_cmlflow](https://assets.ubuntu.com/v1/10c60686-ckf_cmlflow.png)

See [Charmed MLflow documentation](https://documentation.ubuntu.com/charmed-mlflow/) for more details.

### Charmed Feast
CKF integrates with the [Charmed Feast bundle](https://github.com/canonical/charmed-kubeflow-solutions/tree/track/1.10/modules/kubeflow-feast) to provide a feature store for managing and serving machine learning features across training and inference workflows.

![feast_diagram_components|690x366](upload://4sSbWL8eaTppasMFXZleAFxQ61r.png)

From the diagram above:

* The Resource Dispatcher is a component that injects `PodDefaults` and credentials into each user Profile to enable access to the Charmed Feast feature store.
* `PodDefaults` are custom resources that ensure all Pods in a labelled namespace are mutated with required configurations.
* Charmed Feast integrates with the Resource Dispatcher to send its credentials and `feature_store.yaml` configuration to the user namespace. This configuration includes PostgreSQL connection details for the registry, offline store, and online store.

With this integration, users can run Feast commands directly from their Notebook servers to apply feature definitions, materialize data, or retrieve features.

Charmed Feast is also integrated with the central dashboard and served behind the Charmed Kubeflow ingress:

![feast_diagram_integration2|690x190](upload://9uGwhTMOY9SyCNVjPrCSpWdsJV0.png)

See [Charmed Feast documentation](https://canonical-feast-operators.readthedocs-hosted.com/) for more details.

### Canonical Observability Stack

To monitor, alert, and visualize failures and metrics, the Charmed Kubeflow components are individually integrated with [Canonical Observability Stack (COS)](https://documentation.ubuntu.com/observability/).

![cos](https://assets.ubuntu.com/v1/51a9b92a-cos.png)

Due to this integration, each CKF component:

* Enables a metrics endpoint provider for Prometheus to scrape metrics from.
* Has its own Grafana dashboard to visualize relevant metrics.
* Has alert rules that help alert users or administrators when a common failure occurs.
* Integrates with Loki for log reporting.

## Canonical MLOps portfolio

CKF is the foundation of the [Canonical MLOps portfolio](https://ubuntu.com/ai), packaged, secured and maintained by Canonical.

This portfolio is an open-source end-to-end solution that enables the development and deployment of Machine Learning (ML) models in a secure and scalable manner. It is a modular architecture that can be adjusted depending on the use case and consists of a growing set of cloud-native applications.

The solution offers up to ten years of software maintenance break-fix support on selected releases and managed services. 

![mlops](https://assets.ubuntu.com/v1/30f795d5-mlops.png)

From the diagram above:

* Each solution is deployed on its own [Juju model](https://juju.is/docs/juju/model), which is an abstraction that holds applications and their supporting components, such as databases, and network relations.
* Charmed MySQL provides the database support for Charmed Kubeflow and Charmed MLflow applications. It comes pre-bundled within the CKF and Charmed MLflow bundles.
* COS gathers, processes, visualizes, and alerts based on telemetry signals generated by the components that comprise Charmed Kubeflow.
* CKF provides integration with Charmed MLflow capabilities like experiment tracking and model registry.

-------------------------

