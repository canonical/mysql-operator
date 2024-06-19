# Upgrade Juju for new DB revision

Sometimes, the newly released charm revisions [might require a new Juju version](/t/11421),
such information will be clearly indicated in [the release notes](/t/11878) and [available in sources](https://github.com/canonical/mysql-operator/blob/main/metadata.yaml#L67).
Normally, it is necessary to utilize some new Juju features, e.g. [Juju Secrets](https://juju.is/docs/juju/secret), etc.

In this case, Juju informs users about the incompatible combination, and block further changes (keeping the installation safe):
```shell
> juju refresh mysql
Added charm-hub charm "mysql", revision 42 in channel 8.0/stable, to the model
ERROR Charm feature requirements cannot be met:
    - charm requires all of the following:
      - charm requires feature "juju" (version >= 3.1.5) but model currently supports version 3.1.4
```

[The juju controller upgrade is well documented](https://juju.is/docs/juju/manage-controllers#heading--upgrade-a-controller), this tutorial will focus on the practical example.

The [PATCH](https://semver.org/#summary) level Juju changes can be easily applied in-place (and well documented [here](https://juju.is/docs/juju/manage-controllers#heading--upgrade-a-controllers-patch-version), [here](https://juju.is/docs/juju/juju-upgrade-controller) and [here](https://juju.is/docs/juju/juju-upgrade-model)):
```shell
> sudo snap refresh juju 

> juju upgrade-controller
# wait for upgrade controller completed

> juju upgrade-model
# wait for upgrade model completed

> juju refresh mysql
```

In case of [MAJOR/MINOR](https://semver.org/#summary) Juju version upgrade, the easiest way here is to update controller/model to the new version and [migrate](https://juju.is/docs/juju/juju-migrate) the model. Plan:

* Update Juju CLI:
```shell
> juju --version
3.1.8-genericlinux-amd64

> sudo snap refresh juju --channel 3.5/stable # choose necessary version/channel

> juju --version
3.5.1-genericlinux-amd64
```

* Bootstrap the new controller using the necessary version:
```shell
> juju bootstrap lxd lxd_3.5.1 # --agent-version 3.5.1

Creating Juju controller "lxd_3.5.1" on lxd/localhost
Looking for packaged Juju agent version 3.5.1 for amd64
Located Juju agent version 3.5.1-ubuntu-amd64 at https://streams.canonical.com/juju/tools/agent/3.5.1/juju-3.5.1-linux-amd64.tgz
To configure your system to better support LXD containers, please see: https://documentation.ubuntu.com/lxd/en/latest/explanation/performance_tuning/
Launching controller instance(s) on localhost/localhost...
 - juju-374723-0 (arch=amd64)          
Installing Juju agent on bootstrap instance
Waiting for address
Attempting to connect to 10.217.68.44:22
Connected to 10.217.68.44
Running machine configuration script...
Bootstrap agent now started
Contacting Juju controller at 10.217.68.44 to verify accessibility...
Bootstrap complete, controller "lxd_3.5.1" is now available
Controller machines are in the "controller" model
...
```

* Assuming you have database application deploy and running in the old controller `lxd_3.1.8`, model `mydatabase`:
```shell
> juju status
Model       Controller  Cloud/Region         Version  SLA          Timestamp
mydatabase  lxd_3.1.8   localhost/localhost  3.1.8    unsupported  22:54:48+02:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.34-0ubun...  active      3  mysql  8.0/stable  196  no       

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   0        10.217.68.104   3306,33060/tcp  Primary
mysql/1   active    idle   1        10.217.68.118   3306,33060/tcp  
mysql/2   active    idle   2        10.217.68.144   3306,33060/tcp  

Machine  State    Address        Inst id        Base          AZ  Message
0        started  10.217.68.104  juju-a4598a-0  ubuntu@22.04      Running
1        started  10.217.68.118  juju-a4598a-1  ubuntu@22.04      Running
2        started  10.217.68.144  juju-a4598a-2  ubuntu@22.04      Running
```

* Migrate the entire model `mydatabase` to the new controller (no database outage here):
```shell
> juju controllers
Controller  Model       User   Access     Cloud/Region         Models  Nodes    HA  Version
lxd_3.1.8*  mydatabase  admin  superuser  localhost/localhost       2      1  none  3.1.8  
lxd_3.5.1   -           admin  superuser  localhost/localhost       1      1  none  3.5.1

> juju models -c lxd_3.1.8
Controller: lxd_3.1.8
Model        Cloud/Region         Type  Status     Machines  Units  Access  Last connection
controller   localhost/localhost  lxd   available         1      1  admin   just now
mydatabase*  localhost/localhost  lxd   available         3      3  admin   36 seconds ago

> juju models -c lxd_3.5.1
Controller: lxd_3.5.1
Model       Cloud/Region         Type  Status     Machines  Units  Access  Last connection
controller  localhost/localhost  lxd   available         1      1  admin   just now

> juju migrate lxd_3.1.8:mydatabase lxd_3.5.1
Migration started with ID "5f227519-3cdb-4538-871c-1c4589a4598a:0"
```

* The migration process started (see the model status=busy) and at the end of the process the model is no longer available on the old controller as moved to new controller:
```shell
> juju models --controller lxd_3.1.8
...
mydatabase*  localhost/localhost  lxd   busy              3      3  admin   1 minute ago

> juju models --controller lxd_3.1.8
Controller: lxd_3.1.8
Model       Cloud/Region         Type  Status     Machines  Units  Access  Last connection
controller  localhost/localhost  lxd   available         1      1  admin   just now

> juju models --controller lxd_3.5.1
Controller: lxd_3.5.1
Model       Cloud/Region         Type  Status     Machines  Units  Access  Last connection
controller  localhost/localhost  lxd   available         1      1  admin   just now
mydatabase  localhost/localhost  lxd   available         3      3  admin   1 minute ago
```

* The last step is upgrade the model version itself (no database outage here):
```shell
> juju status -m lxd_3.5.1:mydatabase
Model       Controller  Cloud/Region         Version  SLA          Timestamp
mydatabase  lxd_3.5.1   localhost/localhost  3.1.8    unsupported  22:58:10+02:00
...

> juju upgrade-model -m lxd_3.5.1:mydatabase
best version:
    3.5.1
started upgrade to 3.5.1

> juju status -m lxd_3.5.1:mydatabase
Model       Controller  Cloud/Region         Version  SLA          Timestamp
mydatabase  lxd_3.5.1   localhost/localhost  3.5.1    unsupported  22:59:01+02:00
...
```

* At this stage the Juju application continues running under the supervision of the new controller version and can be simply refreshed to the new charm revision ([follow the charm refresh manual to complete the charm upgrade itself](/t/11752)):
```shell
> juju run mysql/leader pre-upgrade-check
> juju refresh mysql
```