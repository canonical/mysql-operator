
# Authentication

This guide describes how authentication works in Charmed Kubeflow (CKF).

All CKF applications and services, including the Kubeflow central dashboard, are centrally exposed through a single ingress, which can also be configured for [TLS](/how-to/manage/enable-https). Since these applications can modify resources in the underlying Kubernetes (K8s) cluster, they require users to be logged in and authenticated to enable proper authorization checks.

Authentication is handled by configuring the central ingress to enforce request authentication via the [OIDC flow](https://openid.net/developers/how-connect-works/). If a request is unauthenticated, the user is redirected to log in. This ensures that access to all CKF applications and resources is restricted to authenticated users.

## Components

Authentication in CKF leverages three components:

* An Identity Provider (IdP), which stores and manages digital identities. It is implemented by the [`dex-auth`](https://charmhub.io/dex-auth) charm. Also referred to as [OpenID Connect](https://openid.net/developers/how-connect-works/) (OIDC) provider.
* An OIDC client, which requests tokens for authentication. It is implemented by the [`oidc-gatekeeper`](https://charmhub.io/oidc-gatekeeper)charm. Also referred to as `AuthService`.
* An ingress, which manages external access to your Kubernetes cluster's services. It is implemented by the [`istio-ingressgateway`](https://charmhub.io/istio-ingressgateway) and [`istio-pilot`](https://charmhub.io/istio-pilot) charms, both needed to configure the [`istio-gateway`](https://charmhub.io/istio-gateway) charm.

These three components participate in the OIDC flow:

![|817x516](https://lh7-rt.googleusercontent.com/docsz/AD_4nXf9QDpJCgvMBmZUdZmSfDoPeTvyd6wp4RScUzraVl18m7EepbF2dD_1acYL_yCbs3RWilizFGyndNUj58jSPLNrp4zuUh4drDE6nHQk1rM48PYZLEQp3GozbejtxAmkfMnM-2sNJQ?key=SrX5YuUQuGxBwuQShTxtGA)

Some important aspects to highlight:

1. The Istio Gateway is configured by an [EnvoyFilter](https://istio.io/latest/docs/reference/config/networking/envoy-filter/), which enforces authentication by forwarding every request made to the Gateway to an AuthService (`oidc-gatekeeper`).

![|441x181](https://lh7-rt.googleusercontent.com/docsz/AD_4nXcIIlC0KAzPN2dwo38HlmI4SdwwOUwb7rCWqJ-Ks8vvDSmh0X3R2NiOL0PVafL7sdtUzn4XMhbJhMvw-Vo-8-yRRK-y9hjw1uY1yYEtPrLQh1J65CWRqztgvUsLhF5tG3ToR9AmDw?key=SrX5YuUQuGxBwuQShTxtGA)

2. The `EnvoyFilter` [template](https://github.com/canonical/istio-operators/blob/main/charms/istio-pilot/src/manifests/auth_filter.yaml.j2) is rendered and applied by `istio-pilot` when integrated with `oidc-gatekeeper` via the `ingress-auth` interface where the latter provides the following data:
  * `service - oidc-gatekeeper`: service name to forward all ingress traffic to.
   * `port`: port of the `service - oidc-gatekeeper`.
   * `allowed-request-headers`: a list of allowed headers to configure the `EnvoyFilter authorisation_request` value, which is always [set to](https://github.com/canonical/oidc-gatekeeper-operator/blob/c420d71465557fbe3419a7ef3b658552b39d9793/src/charm.py#L196C1-L199C23):
```
"allowed-request-headers": [
    "cookie",
    "X-Auth-Token",
],
```
   * `allowed-response-headers`: a list of allowed headers to configure the `EnvoyFilter authorisation_response` value, which is always [set to](https://github.com/canonical/oidc-gatekeeper-operator/blob/c420d71465557fbe3419a7ef3b658552b39d9793/src/charm.py#L200C1-L200C69):
```
"allowed-response-headers": ["kubeflow-userid"]
```

2. `userID` headers are added by the `AuthService` to the original request and are used later in the authorisation process.
4. Dex has a built-in connector that allows the creation of static users. In CKF, this is used for easy access to the dashboard and in development and testing scenarios.

```{note}
Programmatic access with the ingress and `AuthService` can be configured. See [this guide](/how-to/use/perform-inference-on-isvcs-using-access-tokens) for more details.
```

## CKF ingress

The following diagram showcases the CKF ingress flow:

![|901x334](https://lh7-rt.googleusercontent.com/docsz/AD_4nXf8cKGzv2YrrWxv5T1ZEqMnLMeyg6fMjh5Pvub0I06Rt4EQXxrLPcc0i5y_9n1zX6154H742-PbE7STGZXXzWSbjOW13d7qxKSCnfBVEn9PHoS8OoAIsRzUqHXLEV20sLCwXbJp?key=SrX5YuUQuGxBwuQShTxtGA)

1. A user request from outside the cluster is sent, targeting `component-a`.
2. The request is first intercepted by a `LoadBalancer`, only if set up, or the `Service` that is right at the edge of the [Istio Service Mesh](https://istio.io/latest/about/service-mesh/).
4. The request is forwarded to the `Istio Ingress Gateway`, this is the `istio-ingressgateway Service`.
5. The request reaches the `istio-ingressgateway` Pod at the listening port, which is configured by the `Gateway` resource. See [Gateway](https://istio.io/latest/docs/reference/config/networking/gateway/) for more details.
6. The route from the `istio-ingressgateway` Pod to the desired component is configured by a `VirtualService`. See [VirtualService](https://istio.io/latest/docs/reference/config/networking/virtual-service/) for more details.

```{note}
This flow does not consider authentication and [authorisation](/explanation/security/authorisation).
```

Some important aspects to highlight:

1. A [`Gateway`](https://istio.io/latest/docs/reference/config/networking/gateway/) gets created automatically by the `istio-pilot` charm. The `Gateway` Custom Resource (CR) configures the traffic received by the `istio-ingressgateway-xxxx` Pod with:
    * `servers.hosts`: exposed by the Gateway and re-routed to their respective hosts based on the request.
   * TLS: when enabled either via the integration of a TLS certificate provider charm or passing `cert` and `key` values via a [Juju secret](https://documentation.ubuntu.com/juju/3.6/reference/secret/). See [this guide](https://istio.io/latest/docs/tasks/traffic-management/ingress/secure-ingress/#configure-a-tls-ingress-gateway-for-a-single-host) for more details.

```{note}
The [Gateway template](https://github.com/canonical/istio-operators/blob/main/charms/istio-pilot/src/manifests/gateway.yaml.j2) is rendered and applied by the `istio-pilot` charm.
```

2. [`VirtualServices`](https://istio.io/latest/docs/reference/config/networking/virtual-service/) are created to define a set of traffic routes to apply when a host is addressed. In the picture above, whenever a request handled by the `kubeflow-gateway` contains `component-a` in the request, it gets routed to the `component-a` `Service` based on the `VirtualService` routing rules.

A charm that requires a `VirtualService`, for instance, `jupyter-ui` or `kfp-ui`, integrates with `istio-pilot` via the `ingress` interface.

```{note}
The ingress interface is not the same as [this ingress interface](https://github.com/canonical/charm-relation-interfaces/tree/main/interfaces/ingress).
```

The requirer charm shares the following data:

* `prefix`: prefix-based URI to match.
* `rewrite`: used to rewrite the prefix portion of the URI.
* `service`: the `Service` used as the destination of the request.
* `port`: the port of the `Service` used as the destination.

The `VirtualService` [template](https://github.com/canonical/istio-operators/blob/main/charms/istio-pilot/src/manifests/virtual_service.yaml.j2) is rendered and applied by the `istio-pilot` charm in the namespace where Istio is deployed. The `VirtualService` always uses the `kubeflow-gateway` as the `spec.gateways` value. This is not configurable.

3. Kubeflow utilises path-based routing for reaching inside each components APIs, so most components expect the requests to have the format `/<rewrite>/<some>/<route>`, meaning that the request should be forwarded to the component without being prefixed with anything different than what’s defined in the `VirtualService`. For example:
```
curl -v [kubeflow.io/pipeline](http://kubeflow.io/pipelines) -H <some header>
# or from browser [kubeflow.io/pipeline](http://kubeflow.io/pipelines)

# Should be routed as
GET /pipeline/ -H <some header>
```
4. The `istio-ingressgateway` `Deployment` and `Service` are created by the `istio-gateway` charm.
