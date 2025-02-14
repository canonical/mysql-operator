[note]
**Note**: All commands are written for `juju >= v3.1`

If you're using `juju 2.9`, check the [`juju 3.0` Release Notes](https://juju.is/docs/juju/roadmap#heading--juju-3-0-0---22-oct-2022).
[/note]

# Enable tracing
This guide contains the steps to enable tracing with [Grafana Tempo](https://grafana.com/docs/tempo/latest/) for your MySQL application. 

To summarize:
* [Deploy the Tempo charm in a COS K8s environment](#heading--deploy)
* [Offer interfaces for cross-model integrations](#heading--offer)
* [Consume and integrate cross-model integrations](#heading--consume)
* [View MySQL traces on Grafana](#heading--view)


[note type="caution"]
**Warning:** This is feature is in development. It is **not recommended** for production environments. 

This feature is available for Charmed MySQL revision 237+ only.
[/note]

## Prerequisites
Enabling tracing with Tempo requires that you:
- Have deployed a Charmed MySQL application
  - See [How to manage units](https://discourse.charmhub.io/t/charmed-mysql-how-to-manage-units/9904)
- Have deployed a 'cos-lite' bundle from the `latest/edge` track in a Kubernetes environment
  - See [Getting started on MicroK8s](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)

---

<a href="#heading--deploy"><h2 id="heading--deploy"> Deploy Tempo </h2></a>

First, switch to the Kubernetes controller where the COS model is deployed:

```shell
juju switch <k8s_controller_name>:<cos_model_name>
```

Then, deploy the dependencies of Tempo following [this tutorial](https://discourse.charmhub.io/t/tutorial-deploy-tempo-ha-on-top-of-cos-lite/15489). In particular, we would want to:
- Deploy the minio charm
- Deploy the s3 integrator charm
- Add a bucket in minio using a python script
- Configure s3 integrator with the minio credentials

Finally, deploy and integrate with Tempo HA in [a monolithic setup](https://discourse.charmhub.io/t/tutorial-deploy-tempo-ha-on-top-of-cos-lite/15489#heading--deploy-monolithic-setup).

<a href="#heading--offer"><h2 id="heading--offer"> Offer interfaces </h2></a>

Next, offer interfaces for cross-model integrations from the model where Charmed MySQL is deployed.

To offer the Tempo integration, run

```shell
juju offer <tempo_coordinator_k8s_application_name>:tracing
```

Then, switch to the Charmed MySQL VM model, find the offers, and integrate (relate) with them:

```shell
juju switch <machine_controller_name>:<mysql_model_name>

juju find-offers <k8s_controller_name>:  
```
> :exclamation: Do not miss the "`:`" in the command above.

Below is a sample output where `k8s` is the K8s controller name and `cos` is the model where `cos-lite` and `tempo-k8s` are deployed:

```shell
Store  URL                            Access  Interfaces
k8s    admin/cos.tempo                admin   tracing:tracing
```

Next, consume this offer so that it is reachable from the current model:

```shell
juju consume k8s:admin/cos.tempo
```

<a href="#heading--consume"><h2 id="heading--consume"> Consume interfaces </h2></a>

First, deploy [Grafana Agent](https://charmhub.io/grafana-agent) from the `latest/edge` channel:
```shell
juju deploy grafana-agent --channel latest/edge
```

Then, integrate Grafana Agent with Charmed MySQL:
```
juju integrate mysql:cos-agent grafana-agent:cos-agent
```

Finally, integrate Grafana Agent with the consumed interface from the previous section:
```shell
juju integrate grafana-agent:tracing tempo:tracing
```


Wait until the model settles. The following is an example of the `juju status --relations` on the Charmed MySQL model:

```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
database  lxd         localhost/localhost  3.5.4    unsupported  19:15:55Z

SAAS   Status  Store       URL
tempo  active  k8s         admin/cos.tempo

App            Version          Status   Scale  Charm          Channel      Rev  Exposed  Message
grafana-agent                   blocked      1  grafana-agent  latest/edge  282  no       Missing ['grafana-cloud-config']|['grafana-dashboards-provider']|['logging-consumer']|['send-remote-write'] for cos-a...
mysql          8.0.37-0ubun...  active       1  mysql                         0  no       

Unit                Workload  Agent  Machine  Public address  Ports           Message
mysql/0*            active    idle   0        10.205.193.32   3306,33060/tcp  Primary
  grafana-agent/0*  blocked   idle            10.205.193.32                   Missing ['grafana-cloud-config']|['grafana-dashboards-provider']|['logging-consumer']|['send-remote-write'] for cos-a...

Machine  State    Address        Inst id        Base          AZ  Message
0        started  10.205.193.32  juju-4f3e50-0  ubuntu@22.04      Running

Integration provider  Requirer                 Interface              Type         Message
grafana-agent:peers   grafana-agent:peers      grafana_agent_replica  peer         
mysql:cos-agent       grafana-agent:cos-agent  cos_agent              subordinate  
mysql:database-peers  mysql:database-peers     mysql_peers            peer         
mysql:restart         mysql:restart            rolling_op             peer         
mysql:upgrade         mysql:upgrade            upgrade                peer         
tempo:tracing         grafana-agent:tracing    tracing                regular  
```

[note]
**Note:** All traces are exported to Tempo using HTTP. Support for sending traces via HTTPS is an upcoming feature.
[/note]

<a href="#heading--view"><h2 id="heading--view"> View traces </h2></a>

After this is complete, the Tempo traces will be accessible from Grafana under the `Explore` section with `tempo-k8s` as the data source. You will be able to select `mysql` as the `Service Name` under the `Search` tab to view traces belonging to Charmed MySQL.

Below is a screenshot demonstrating a Charmed MySQL trace:

![Example MySQL trace with Grafana Tempo|690x378](upload://nzIU9vclqmeqwFSF1eV1xKhK6fY.png)

Feel free to read through the [Tempo HA documentation](https://discourse.charmhub.io/t/charmed-tempo-ha/15531) at your leisure to explore its deployment and its integrations.