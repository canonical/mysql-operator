
# Deploy on LXD

This guide assumes you have a running Juju and LXD environment. 

For a detailed walkthrough of setting up an environment and deploying the charm on LXD, refer to the [Tutorial](/tutorial/index).

---

[Bootstrap](https://juju.is/docs/juju/juju-bootstrap) a juju controller and create a [model](https://juju.is/docs/juju/juju-add-model) if you haven't already:
```shell
juju bootstrap localhost <controller name>
juju add-model <model name>
```
Deploy MySQL
```shell
juju deploy mysql --channel 8.0/stable
```
> See the [`juju deploy` documentation](https://juju.is/docs/juju/juju-deploy) for all available options at deploy time.
> 
> See the [Configurations tab](https://charmhub.io/mysql/configurations) for specific MySQL parameters.

Sample output of `juju status --watch 1s`:
```shell
Model   Controller  Cloud/Region         Version  SLA          Timestamp
mysql   overlord    localhost/localhost  3.1.6    unsupported  00:52:59+02:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.32-0ubun...  active      1  mysql  8.0/stable  151  no       Primary

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   1        10.234.188.135  3306,33060/tcp  Primary

Machine  State    Address         Inst id        Base          AZ  Message
1        started  10.234.188.135  juju-ff9064-0  ubuntu@22.04      Running
```

