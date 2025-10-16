# Deploy charm module

## Install Terraform tooling

This guide assumes Juju is installed, and you have an LXD controller already bootstrapped. For more information, check the [Charmed MySQL tutorial](/tutorial/index).

Let's install Terraform Provider and example modules:
```shell
sudo snap install terraform --classic
```

Switch to the LXD provider and create a new model:
```shell
juju switch lxd
juju add-model my-model
```

Clone the MySQL operator repository and navigate to the terraform module:
```shell
git clone https://github.com/canonical/mysql-operator.git
cd terraform
```

Initialise the Juju Terraform Provider:
```shell
terraform init
```

## Verify the deployment

Open the `main.tf` file to see the brief contents of the Terraform module, and run `terraform plan` to get a preview of the changes that will be made:

```shell
terraform plan -var 'model_name=my-model'
```

## Apply the deployment

If everything looks correct, deploy the resources (skip the approval):

```shell
terraform apply -auto-approve -var 'model_name=my-model'
```

## Check deployment status

Check the deployment status with 

```shell
juju status --model lxd:my-model --watch 1s
```

Sample output:

```shell
Model     Controller      Cloud/Region         Version  SLA          Timestamp
my-model  lxd-controller  localhost/localhost  3.5.3    unsupported  12:49:34Z

App    Version          Status  Scale  Charm  Channel     Rev  Exposed  Message
mysql  8.0.41-0ubun...  active      1  mysql  8.0/stable  366  no

Unit      Workload  Agent  Machine  Public address  Ports           Message
mysql/0*  active    idle   0        10.101.248.220  3306,33060/tcp  Primary

Machine  State    Address         Inst id        Base          AZ  Message
0        started  10.101.248.220  juju-c4a403-0  ubuntu@22.04      Running
```

Continue to operate the charm as usual from here or apply further Terraform changes.

## Clean up

To keep the house clean, remove the newly deployed MySQL charm by running
```shell
terraform destroy -var 'model_name=my-model'
```

---

Feel free to [contact us](/reference/contacts) if you have any question and collaborate with us on GitHub!
