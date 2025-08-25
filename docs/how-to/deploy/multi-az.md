
# Deploy on multiple availability zones (AZ) 

During the deployment to hardware/VMs, it is important to spread all the
database copies (Juju units) to different hardware servers,
or even better, to the different [availability zones](https://en.wikipedia.org/wiki/Availability_zone) (AZ). This will guarantee no shared service-critical components across the DB cluster (eliminate the case with all eggs in the same basket).

This guide will take you through deploying a MySQL cluster on GCE using 3 available zones. All Juju units will be set up to sit in their dedicated zones only, which effectively guarantees database copy survival across all available AZs.

```{note}
This documentation assumes that your cloud supports and provides availability zones concepts. This is enabled by default on EC2/GCE and supported by LXD/MicroCloud.
```

## Set up GCE on Google Cloud

Let's deploy the [MySQL Cluster on GCE (us-east4)](/how-to/deploy/gce) using all 3 zones there (`us-east4-a`, `us-east4-b`, `us-east4-c`) and make sure all pods always sits in the dedicated zones only.

```{caution}
Creating the following GKE resources may cost you money - be sure to monitor your GCloud costs.
```

Log into Google Cloud and [bootstrap GCE on Google Cloud](/how-to/deploy/gce):

```shell
gcloud auth login
gcloud iam service-accounts keys create sa-private-key.json  --iam-account=juju-gce-account@[your-gcloud-project-12345].iam.gserviceaccount.com
sudo mv sa-private-key.json /var/snap/juju/common/sa-private-key.json
sudo chmod a+r /var/snap/juju/common/sa-private-key.json

juju add-credential google
juju bootstrap google gce
juju add-model mymodel
```

## Deploy MySQL with Juju zones constraints

Juju provides the support for availability zones using **constraints**. Read more about zones in [Juju documentation](https://juju.is/docs/juju/constraint#zones).

The command below demonstrates how Juju automatically deploys Charmed MySQL VM using [Juju constraints](https://juju.is/docs/juju/constraint#zones):

```shell
juju deploy mysql -n 3 \
  --constraints zones=us-east1-b,us-east1-c,us-east1-d
```

After a successful deployment, `juju status` will show an active application:

```shell
Model    Controller  Cloud/Region     Version    SLA          Timestamp
mymodel  gce         google/us-east1  3.6-rc1.1  unsupported  00:59:53+02:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.36-0ubun...  active      3  mysql  8.0/stable  240  no       

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0   active    idle   0        34.23.202.220   3306,33060/tcp  
mysql/1*  active    idle   1        34.148.44.51    3306,33060/tcp  Primary
mysql/2   active    idle   2        34.23.252.144   3306,33060/tcp  

Machine  State    Address        Inst id        Base          AZ          Message
0        started  34.23.202.220  juju-5fe1b7-0  ubuntu@22.04  us-east1-c  RUNNING
1        started  34.148.44.51   juju-5fe1b7-1  ubuntu@22.04  us-east1-d  RUNNING
2        started  34.23.252.144  juju-5fe1b7-2  ubuntu@22.04  us-east1-b  RUNNING
```

and each unit/vm will sit in the separate AZ out of the box:
```shell
> gcloud compute instances list

NAME           ZONE        MACHINE_TYPE  PREEMPTIBLE  INTERNAL_IP  EXTERNAL_IP    STATUS
juju-5fe1b7-2  us-east1-b  e2-highcpu-2               10.142.0.38  34.23.252.144  RUNNING  # mysql/2
juju-81e41f-0  us-east1-b  n1-highcpu-4               10.142.0.35  34.138.167.85  RUNNING  # Juju Controller
juju-5fe1b7-0  us-east1-c  e2-highcpu-2               10.142.0.36  34.23.202.220  RUNNING  # mysql/0
juju-5fe1b7-1  us-east1-d  e2-highcpu-2               10.142.0.37  34.148.44.51   RUNNING  # mysql/1
```

### Simulation: A node gets lost
Let's destroy a GCE node and recreate it using the same AZ (Primary MySQL unit is being removed):
```shell
> gcloud compute instances delete juju-5fe1b7-1
No zone specified. Using zone [us-east1-d] for instance: [juju-5fe1b7-1].
The following instances will be deleted. Any attached disks configured to be auto-deleted will be deleted unless they are attached to any other instances or the `--keep-disks` flag is given and specifies them for keeping. Deleting a disk is 
irreversible and any data on the disk will be lost.
 - [juju-5fe1b7-1] in [us-east1-d]

Do you want to continue (Y/n)?  Y

Deleted [https://www.googleapis.com/compute/v1/projects/data-platform-testing-354909/zones/us-east1-d/instances/juju-5fe1b7-1].
```

The new MySQL Primary elected automatically:
```shell
Model    Controller  Cloud/Region     Version    SLA          Timestamp
mymodel  gce         google/us-east1  3.6-rc1.1  unsupported  01:03:13+02:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.36-0ubun...  active    2/3  mysql  8.0/stable  240  no       

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   0        34.23.202.220   3306,33060/tcp  Primary
mysql/1   unknown   lost   1        34.148.44.51    3306,33060/tcp  agent lost, see 'juju show-status-log mysql/1'
mysql/2   active    idle   2        34.23.252.144   3306,33060/tcp  

Machine  State    Address        Inst id        Base          AZ          Message
0        started  34.23.202.220  juju-5fe1b7-0  ubuntu@22.04  us-east1-c  RUNNING
1        down     34.148.44.51   juju-5fe1b7-1  ubuntu@22.04  us-east1-d  RUNNING
2        started  34.23.252.144  juju-5fe1b7-2  ubuntu@22.04  us-east1-b  RUNNING
```

Here we should remove the no longer available `server/vm/GCE` node and add a new one. Juju will create it in the same AZ `us-east4-c`:
```shell
> juju remove-unit mysql/1 --force --no-wait --no-prompt
WARNING This command will perform the following actions:
will remove unit mysql/1
```

The command `juju status` shows the machines in a healthy state, but MySQL HA recovery is necessary:
```shell
Model    Controller  Cloud/Region     Version    SLA          Timestamp
mymodel  gce         google/us-east1  3.6-rc1.1  unsupported  01:04:42+02:00

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.36-0ubun...  active      2  mysql  8.0/stable  240  no       

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   0        34.23.202.220   3306,33060/tcp  Primary
mysql/2   active    idle   2        34.23.252.144   3306,33060/tcp  

Machine  State    Address        Inst id        Base          AZ          Message
0        started  34.23.202.220  juju-5fe1b7-0  ubuntu@22.04  us-east1-c  RUNNING
2        started  34.23.252.144  juju-5fe1b7-2  ubuntu@22.04  us-east1-b  RUNNING
```

Request Juju to add a new unit in the proper AZ:
```shell
juju add-unit mysql -n 1
```

Juju uses the right AZ where the node is missing. Run `juju status`:
```shell
Model    Controller  Cloud/Region     Version    SLA          Timestamp
mymodel  gce         google/us-east1  3.6-rc1.1  unsupported  01:05:12+02:00

App    Version  Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql           active    2/3  mysql  8.0/stable  240  no       

Unit      Workload  Agent       Machine  Public address  Ports           Message
mysql/0*  active    idle        0        34.23.202.220   3306,33060/tcp  Primary
mysql/2   active    idle        2        34.23.252.144   3306,33060/tcp  
mysql/3   waiting   allocating  3                                        waiting for machine

Machine  State    Address        Inst id        Base          AZ          Message
0        started  34.23.202.220  juju-5fe1b7-0  ubuntu@22.04  us-east1-c  RUNNING
2        started  34.23.252.144  juju-5fe1b7-2  ubuntu@22.04  us-east1-b  RUNNING
3        pending                 juju-5fe1b7-3  ubuntu@22.04  us-east1-d  starting
```

## Remove GCE setup

```{caution}
**Warning**: Do not forget to remove your test setup - it can be costly!
```

Check the list of currently running GCE instances:
```shell
> gcloud compute instances list
NAME           ZONE        MACHINE_TYPE  PREEMPTIBLE  INTERNAL_IP  EXTERNAL_IP    STATUS
juju-5fe1b7-2  us-east1-b  e2-highcpu-2               10.142.0.38  34.23.252.144  RUNNING
juju-81e41f-0  us-east1-b  n1-highcpu-4               10.142.0.35  34.138.167.85  RUNNING
juju-5fe1b7-0  us-east1-c  e2-highcpu-2               10.142.0.36  34.23.202.220  RUNNING
juju-5fe1b7-3  us-east1-d  e2-highcpu-2               10.142.0.39  34.148.44.51   RUNNING
```

Request Juju to clean all GCE resources:
```shell
juju destroy-controller gce --no-prompt --force --destroy-all-models
```

Re-check that there are no running GCE instances left (it should be empty):
```shell
gcloud compute instances list
```

