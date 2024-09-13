# Deploy Charmed MySQL

Please follow the [Tutorial](/t/9922) to deploy the charm on LXD.

Short story for your Ubuntu 22.04 LTS:
```shell
sudo snap install multipass
multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev # tune CPU/RAM/HDD accordingly to your needs
multipass shell my-vm

juju add-model mysql
juju deploy mysql --channel 8.0/stable # --config profile=testing
juju status --watch 1s
```

The expected result:
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

Check the [Testing](/t/11770) reference to test your deployment.