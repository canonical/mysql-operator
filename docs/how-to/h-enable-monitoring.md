# Enable monitoring
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` and `juju integrate` with `juju relate` for Juju 2.9.

Enable monitoring requires that you:
* [Have a Charmed MySQL deployed](/t/9904)
* [Deploy 'cos-lite' bundle in a Kubernetes environment](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)

Switch to COS K8s environment and offer COS interfaces to be cross-model integrated (related) with Charmed MySQL VM model:
```shell
# Switch to Kubernetes controller, for the cos model.
juju switch <k8s_controller>:<cos_model_name>

juju offer grafana:grafana-dashboard
juju offer loki:logging
juju offer prometheus:receive-remote-write
```

Switch to Charmed MySQL VM model, find offers and integrate (relate) with them:
```shell
# We are on the Kubernetes controller, for the cos model. Switch to mysql model
juju switch <machine_controller_name>:<mysql_model_name>

juju find-offers <k8s_controller>: # Do not miss ':' here!
```

A similar output should appear, if `k8s` is the k8s controller name and `cos` the model where `cos-lite` has been deployed:
```shell
Store  URL                    Access  Interfaces
k8s    admin/cos.grafana      admin   grafana:grafana-dashboard
k8s    admin/cos.loki         admin   loki:logging
k8s    admin/cos.prometheus   admin   prometheus:receive-remote-write
...
```

Consume offers to be reachable in the current model:
```shell
juju consume k8s:admin/cos.grafana
juju consume k8s:admin/cos.loki
juju consume k8s:admin/cos.prometheus
```

Now, deploy '[grafana-agent](https://charmhub.io/grafana-agent)' (subordinate charm) and integrate (relate) it with Charmed MySQL, later integrate (relate) `grafana-agent` with consumed COS offers:
```shell
juju deploy grafana-agent
juju integrate grafana-agent mysql:cos-agent 
juju integrate grafana-agent grafana
juju integrate grafana-agent loki
juju integrate grafana-agent prometheus
```

After this is complete, Grafana will show the new dashboards: `MySQL Exporter` and allows access for Charmed MySQL logs on Loki.

The example of `juju status` on Charmed MySQL VM model:
```shell
ubuntu@localhost:~$ juju status
Model      Controller  Cloud/Region         Version  SLA          Timestamp
vmmodel    local       localhost/localhost  3.1.6    unsupported  00:12:18+02:00

SAAS         Status  Store    URL
grafana      active  k8s      admin/cos.grafana
loki         active  k8s      admin/cos.loki
prometheus   active  k8s      admin/cos.prometheus

App                   Version      Status  Scale  Charm               Channel   Rev  Exposed  Message
grafana-agent                      active      1  grafana-agent       edge        5  no
mysql                 8.0.32       active      1  mysql               8.0/edge  144  no       Primary

Unit                          Workload  Agent  Machine  Public address  Ports               Message
mysql/3*                      active    idle   4        10.85.186.140   3306/tcp,33060/tcp  Primary
  grafana-agent/0*            active    idle            10.85.186.140

Machine  State    Address        Inst id        Series  AZ  Message
4        started  10.85.186.140  juju-fcde9e-4  jammy       Running
```

The example of `juju status` on COS K8s model:
```shell
ubuntu@localhost:~$ juju status
Model  Controller   Cloud/Region        Version  SLA          Timestamp
cos    k8s          microk8s/localhost  3.1.6    unsupported  00:15:31+02:00

App           Version  Status  Scale  Charm             Channel  Rev  Address         Exposed  Message
alertmanager  0.23.0   active      1  alertmanager-k8s  stable    47  10.152.183.206  no
catalogue              active      1  catalogue-k8s     stable    13  10.152.183.183  no
grafana       9.2.1    active      1  grafana-k8s       stable    64  10.152.183.140  no
loki          2.4.1    active      1  loki-k8s          stable    60  10.152.183.241  no
prometheus    2.33.5   active      1  prometheus-k8s    stable   103  10.152.183.240  no
traefik       2.9.6    active      1  traefik-k8s       stable   110  10.76.203.178   no

Unit             Workload  Agent  Address      Ports  Message
alertmanager/0*  active    idle   10.1.84.125
catalogue/0*     active    idle   10.1.84.127
grafana/0*       active    idle   10.1.84.83
loki/0*          active    idle   10.1.84.79
prometheus/0*    active    idle   10.1.84.96
traefik/0*       active    idle   10.1.84.119

Offer        Application  Charm           Rev  Connected  Endpoint              Interface                Role
grafana      grafana      grafana-k8s     64   1/1        grafana-dashboard     grafana_dashboard        requirer
loki         loki         loki-k8s        60   1/1        logging               loki_push_api            provider
prometheus   prometheus   prometheus-k8s  103  1/1        receive-remote-write  prometheus_remote_write  provider
```

To connect Grafana WEB interface, follow the COS section "[Browse dashboards](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)":
```shell
juju run grafana/leader get-admin-password --model <k8s_controller>:<cos_model_name>
```