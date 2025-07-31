
# Authorisation

This guide describes how authorisation works in Charmed Kubeflow (CKF).

Authorisation is provided through the integration between Kubeflow and [Kubernetes (K8s) role-based access control (RBAC)](https://kubernetes.io/docs/reference/access-authn-authz/rbac/), as well as [Istio Authorization Policy](https://istio.io/latest/docs/reference/config/security/authorization-policy/).

Kubeflow's authorisation is designed to allow users to access resources within their own namespaces, either via the Kubernetes API (using [`kubectl`](https://kubernetes.io/docs/reference/kubectl/)) or through network requests (`GET dashboard.io/pipeline` or in-cluster requests to other user namespace resources).

## Components

The components involved are the following:

* Kubeflow Profiles: a [K8s Custom Resource Definition (CRD)](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/#customresourcedefinitions) that provides namespace isolation based on K8s RBAC. Profiles are owned by single users, but can have multiple contributors with view and/or edit access.
  * Profiles are managed by the Kubeflow profiles controller, implemented by the [`kubeflow-profiles` charm](https://charmhub.io/kubeflow-profiles).
  * Contributors are managed by the [Kubeflow Access Management API (KFAM)](https://github.com/kubeflow/kubeflow/tree/master/components/access-management), also implemented by the `kubeflow-profiles` charm.
* K8s RBAC.
* K8s `SubjectAccessReview` API, see [Authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/#request-attributes-used-in-authorization) for more information.
* [Istio Authorization Policies](https://istio.io/latest/docs/reference/config/security/authorization-policy/).

## Kubeflow profiles

When a new profile is created, each resource gets the following:

* A `Namespace`, matching the profile name.
* `RoleBindings` for the profile owners to `ClusterRole/kubeflow-admin`, created by default by the `kubeflow-roles` charm. Similar `RoleBindings` are set for the `ServiceAccount` level.
* `RoleBindings` for the profile contributors to `ClusterRole/kubeflow-{ROLE}`.
* Istio `AuthorizationPolicies` for the profile owner and for the contributor(s).

See [Profile resources](https://www.kubeflow.org/docs/components/central-dash/profiles/#profile-resources) for more details. Refer to [Manage profiles](/how-to/manage/manage-profiles) to learn how to administer profiles in CKF.

## Authorisation flows

There are two main use cases for authorisation flows.

### Managing resources via the UI

The most common use case for authorization occurs when users navigate CKF through the central dashboard User Interface (UI) in their browser.

CKF is composed of multiple web app microservices for managing different resources, such as Notebooks, Pipelines, Katib experiments, all accessible through the dashboard. The backends of these microservices follow the same authorization logic and operate on user resources in various namespaces on the users' behalf.

Specifically, when a user clicks on the Notebooks page and views the list of Notebooks, the following steps occur under the hood:

1. The browser makes a request to the API of the Notebooks web app:
* This API endpoint is exposed via the central Ingress.
* The browser includes the login cookie in the request.
* The endpoint is `/jupyter/api/namespaces/ml-engineers/notebooks`.

2. The request reaches the Ingress Gateway, where authentication checks are performed.
3. Once authenticated, a `kubeflow-userid` header is added to the request.

![|678x322](https://lh7-rt.googleusercontent.com/docsz/AD_4nXf1Z3AvHRUbutRIGBAHKqxRAzwv_-_Z1hMlMEGIdrJGtolOZVqhGgu5XTzfjqPWvWM3uNCcQp1GOvB5qZ-0CKrREqi5h0c4Cen9I9fYMLOtwwTXlxXS5huYUYMYNSLhSszKbQWypQ?key=thQMQkfqmHa8NJjXMfGJGw)

4. The request is forwarded to the Notebooks web app backend inside the cluster.
5. The backend receives a request indicating that a certain user, defined in the `kubeflow-userid` header, wants to list Notebooks in the `ml-engineers` namespace.
6. The backend performs a `SubjectAccessReview` to verify that the user is authorized to list Notebooks in that namespace, according to K8s RBAC.
7. If authorized, the backend performs a list request to K8s for the Notebooks in the `ml-engineers` namespace and returns the result.

![|769x291](https://lh7-rt.googleusercontent.com/docsz/AD_4nXfj07hyme3c-Gnqmlto61YN4Su3_BlRlDhbMhmrpxIhhnPJweDQQgAzcSTpTSB3vTRnCDm_NjunHOKI84jdkGn9-MZQs9QOJ8zOWMXrPKtguukEEBYxx-BODaqJTMTVDboT2YNn?key=thQMQkfqmHa8NJjXMfGJGw)

```{note}
Users could forge a request from their browser to access the Notebooks web app, attempting to retrieve Notebooks from a different namespace. In such cases, if the user does not have RBAC permissions for the target namespace, the `SubjectAccessReview` catches this, and the Notebooks web app will return a 403 Forbidden response.
```

```{note}
All backends are `super-privileged` and can manipulate resources in any namespace. However, they use `SubjectAccessReviews` to ensure they do not escalate permissions or allow users to perform actions in namespaces for which they lack authorization.
```

### In-cluster user workloads

While interacting with Kubeflow’s UIs, users can create workload Pods that run inside the Kubeflow cluster. From within those workloads, users can interact with the K8s API using tools such as [`kubectl`](https://kubernetes.io/docs/reference/kubectl/).

All user workloads running in namespaces associated with a Profile are Pods whose identity is defined by a `ServiceAccount`. Most workloads in user namespaces use the `default-editor` `ServiceAccount`.

As a result, when `kubectl` is used from within those workloads, the credentials used are those of the `ServiceAccount` token. This means RBAC policies are enforced for every request made from these workloads, and users cannot arbitrarily perform Create-Read-Update-Delete (CRUD) operations on K8s resources in other namespaces.

```{note}

The `default-editor` `ServiceAccount` has permission to modify all Kubeflow resources and many common K8s resources, such as Pods and Services, within its own namespace.

```

-------------------------

