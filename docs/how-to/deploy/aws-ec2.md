
# How to deploy on AWS EC2

[Amazon Web Services](https://aws.amazon.com/) is a popular subsidiary of Amazon that provides on-demand cloud computing platforms on a metered pay-as-you-go basis. Access the AWS web console at [console.aws.amazon.com](https://console.aws.amazon.com/).

## Install AWS and Juju tooling

Install Juju via snap:
```shell
sudo snap install juju
```

Follow the installation guides for:
* [AWs CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) - the Amazon Web Services CLI

To check they are all correctly installed, you can run the commands demonstrated below with sample outputs:

```console
~$ juju version
3.5.4-genericlinux-amd64

~$ aws --version
aws-cli/2.13.25 Python/3.11.5 Linux/6.2.0-33-generic exe/x86_64.ubuntu.23 prompt/off
```
### Authenticate
[Create an IAM account](https://docs.aws.amazon.com/eks/latest/userguide/getting-started-console.html) (or use legacy access keys) to operate AWS EC2:
```shell
mkdir -p ~/.aws && cat <<- EOF >  ~/.aws/credentials.yaml
credentials:
  aws:
    NAME_OF_YOUR_CREDENTIAL:
      auth-type: access-key
      access-key: SECRET_ACCESS_KEY_ID
      secret-key: SECRET_ACCESS_KEY_VALUE
EOF
```

## Bootstrap Juju controller on AWS EC2

Add AWS credentials to Juju:
```shell
juju add-credential aws -f ~/.aws/credentials.yaml
```
Bootstrap Juju controller ([check all supported configuration options](https://juju.is/docs/juju/amazon-ec2)):
```shell
juju bootstrap aws
```
[details="Output example"]
```shell
> juju bootstrap aws
Creating Juju controller "aws-us-east-1" on aws/us-east-1
Looking for packaged Juju agent version 3.5.4 for amd64
Located Juju agent version 3.5.4-ubuntu-amd64 at https://juju-dist-aws.s3.amazonaws.com/agents/agent/3.5.4/juju-3.5.4-linux-amd64.tgz
Launching controller instance(s) on aws/us-east-1...
 - i-0f4615983d113166d (arch=amd64 mem=8G cores=2)           
Installing Juju agent on bootstrap instance
Waiting for address
Attempting to connect to 54.226.221.6:22
Attempting to connect to 172.31.20.34:22
Connected to 54.226.221.6
Running machine configuration script...
Bootstrap agent now started
Contacting Juju controller at 54.226.221.6 to verify accessibility...

Bootstrap complete, controller "aws-us-east-1" is now available
Controller machines are in the "controller" model

Now you can run
	juju add-model <model-name>
to create a new model to deploy workloads.
```
[/details]

You can check the [AWS EC2 instance availability](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#Instances:instanceState=running) (ensure the right AWS region chosen!):
![image|690x118](upload://putAO5NyHdaeWE6jXI8X1hZHTYv.png)

Create a new Juju model:
```shell
juju add-model welcome
```
> (Optional) Increase the debug level if you are troubleshooting charms:
> ```shell
> juju model-config logging-config='<root>=INFO;unit=DEBUG'
> ```

## Deploy charms

The following command deploys MySQL and [Data-Integrator](https://charmhub.io/data-integrator) (the charm to request a test DB):

```shell
juju deploy mysql
juju deploy data-integrator --config database-name=test123
juju relate mysql data-integrator
```
Check the status:
```shell
> juju status --relations
Model    Controller     Cloud/Region   Version  SLA          Timestamp
welcome  aws-us-east-1  aws/us-east-1  3.5.4    unsupported  17:52:25+02:00

App              Version          Status  Scale  Charm            Channel        Rev  Exposed  Message
data-integrator                   active      1  data-integrator  latest/stable   41  no       
mysql            8.0.36-0ubun...  active      3  mysql            8.0/stable     240  no       

Unit                Workload  Agent  Machine  Public address  Ports           Message
data-integrator/1*  active    idle   9        34.207.85.249                   
mysql/0*            active    idle   6        107.21.70.243   3306,33060/tcp  Primary
mysql/1             active    idle   7        3.82.62.144     3306,33060/tcp  
mysql/2             active    idle   8        44.193.79.253   3306,33060/tcp  

Machine  State    Address        Inst id              Base          AZ          Message
6        started  107.21.70.243  i-0db4d16715a59f74d  ubuntu@22.04  us-east-1a  running
7        started  3.82.62.144    i-038a7ca89b40f83bf  ubuntu@22.04  us-east-1b  running
8        started  44.193.79.253  i-01dc0ad71d5607fdb  ubuntu@22.04  us-east-1c  running
9        started  34.207.85.249  i-068d4d0d8b7ede754  ubuntu@22.04  us-east-1d  running

Integration provider                   Requirer                               Interface              Type     Message
data-integrator:data-integrator-peers  data-integrator:data-integrator-peers  data-integrator-peers  peer     
mysql:database                         data-integrator:mysql                  mysql_client           regular  
mysql:database-peers                   mysql:database-peers                   mysql_peers            peer     
mysql:restart                          mysql:restart                          rolling_op             peer     
mysql:upgrade                          mysql:upgrade                          upgrade                peer     
```

Once deployed, request the credentials for your newly bootstrapped MySQL database.

For Juju 2.9 use:
```shell
juju run-action --wait data-integrator/leader get-credentials
```
and for newer Juju 3+ use:
```shell
juju run data-integrator/leader get-credentials
```

The output example:
```shell
mysql:
  data: '{"database": "test123", "external-node-connectivity": "true", "requested-secrets":
    "[\"username\", \"password\", \"tls\", \"tls-ca\", \"uris\"]"}'
  database: test123
  endpoints: 172.31.16.250:3306
  password: e7vOMyzj2FnrBDnXZdXScEOc
  read-only-endpoints: 172.31.10.167:3306,172.31.39.202:3306
  username: relation-16
  version: 8.0.36-0ubuntu0.22.04.1
ok: "True"
```

At this point, you can access your DB inside AWS using the internal IP address. All further Juju applications will use the database through the internal network:
```shell
> mysql -h 172.31.16.250 -P 3306 -u relation-16 -pe7vOMyzj2FnrBDnXZdXScEOc test123 
...
mysql> show databases;
+--------------------+
| Database           |
+--------------------+
| information_schema |
| performance_schema |
| test123            |
+--------------------+
3 rows in set (0.00 sec)
```

From here you can [use/scale/backup/restore/refresh](/tutorial/index) your newly deployed Charmed MySQL.

## Expose database (optional)

If necessary to access DB from outside of AWS (warning: [opening ports to public is risky](https://www.beyondtrust.com/blog/entry/what-is-an-open-port-what-are-the-security-implications)) open the AWS firewall using the simple [juju expose](https://juju.is/docs/juju/juju-expose) functionality: 
```shell
juju expose mysql
```

Once exposed, you can connect your database using the same credentials as above (Important: this time use the EC2 Public IP assigned to the MySQL instance):
```shell
> juju status mysql
...
Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   6        107.21.70.243   3306,33060/tcp  Primary
...

> mysql -h 107.21.70.243 -P 3306 -u relation-16 -pe7vOMyzj2FnrBDnXZdXScEOc test123 
...
mysql> show databases;
+--------------------+
| Database           |
+--------------------+
| information_schema |
| performance_schema |
| test123            |
+--------------------+
3 rows in set (0.13 sec)
```

To close the public access run:
```shell
juju unexpose mysql
```
## Clean up

```{caution}
Always clean AWS resources that are no longer necessary -  they could be costly!
```

To destroy the Juju controller and remove AWS instance (warning: all your data will be permanently removed):
```shell
> juju controllers
Controller      Model  User   Access     Cloud/Region   Models  Nodes    HA  Version
aws-us-east-1*  -      admin  superuser  aws/us-east-1       1      1  none  3.5.4  

> juju destroy-controller aws-us-east-1 --destroy-all-models --destroy-storage --force
```

Next, check and manually delete all unnecessary AWS EC2 instances, to show the list of all your EC2 instances run the following command (make sure the correct region used!): 
```shell
aws ec2 describe-instances --region us-east-1 --query "Reservations[].Instances[*].{InstanceType: InstanceType, InstanceId: InstanceId, State: State.Name}" --output table
```
[details="Output example"]
```shell
-------------------------------------------------------
|                  DescribeInstances                  |
+---------------------+----------------+--------------+
|     InstanceId      | InstanceType   |    State     |
+---------------------+----------------+--------------+
|  i-0f374435695ffc54c|  m7i.large     |  terminated  |
|  i-0e1e8279f6b2a08e0|  m7i.large     |  terminated  |
|  i-061e0d10d36c8cffe|  m7i.large     |  terminated  |
|  i-0f4615983d113166d|  m7i.large     |  terminated  |
+---------------------+----------------+--------------+
```
[/details]

List your Juju credentials:
```shell
> juju credentials
...
Client Credentials:
Cloud        Credentials
aws          NAME_OF_YOUR_CREDENTIAL
...
```
Remove AWS EC2 CLI credentials from Juju:
```shell
> juju remove-credential aws NAME_OF_YOUR_CREDENTIAL
```

Finally, remove AWS CLI user credentials (to avoid forgetting and leaking):
```shell
rm -f ~/.aws/credentials.yaml
```

