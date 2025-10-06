
# How to deploy using Terraform

[Terraform](https://www.terraform.io/) is an infrastructure automation tool to provision and manage resources in clouds or data centers.
To deploy Charmed MySQL using Terraform and Juju, you can use the [Juju Terraform Provider](https://registry.terraform.io/providers/juju/juju/latest). 

For an in-depth introduction to the Juju Terraform Provider, read [this Discourse post](https://discourse.charmhub.io/t/6939).

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
terraform plan -var "model_name=my-model"
```

## Apply the deployment

If everything looks correct, deploy the resources (skip the approval):

```shell
terraform apply -auto-approve -var "model_name=my-model"
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
mysql/0*  active    idle   0        10.101.248.225  3306,33060/tcp  Primary                           

Machine  State    Address         Inst id        Base          AZ  Message
0        started  10.101.248.225  juju-c4a403-0  ubuntu@22.04      Running   
```

Continue to operate the charm as usual from here or apply further Terraform changes.

## Clean up

To keep the house clean, remove the newly deployed MySQL charm by running
```shell
terraform destroy -var "model_name=my-model"
```

Sample output:
```shell
juju_application.mysql_server: Refreshing state... [id=my-model:mysql]

Terraform used the selected providers to generate the following execution plan. Resource actions are indicated with the following symbols:
  - destroy

Terraform will perform the following actions:

  # juju_application.mysql_server will be destroyed
  - resource "juju_application" "mysql_server" {
      - constraints = "arch=amd64" -> null
      - id          = "my-model:mysql" -> null
      - model       = "my-model" -> null
      - name        = "mysql" -> null
      - placement   = "0" -> null
      - storage     = [
          - {
              - count = 1 -> null
              - label = "database" -> null
              - pool  = "rootfs" -> null
              - size  = "10G" -> null
            },
        ] -> null
      - trust       = true -> null
      - units       = 1 -> null

      - charm {
          - base     = "ubuntu@22.04" -> null
          - channel  = "8.0/stable" -> null
          - name     = "mysql" -> null
          - revision = 366 -> null
          - series   = "jammy" -> null
        }
    }

Plan: 0 to add, 0 to change, 1 to destroy.

Changes to Outputs:
  - application_name = "mysql" -> null

Do you really want to destroy all resources?
  Terraform will destroy all your managed infrastructure, as shown above.
  There is no undo. Only 'yes' will be accepted to confirm.

  Enter a value: yes

juju_application.mysql_server: Destroying... [id=my-model:mysql]
juju_application.mysql_server: Destruction complete after 0s

Destroy complete! Resources: 1 destroyed.
```

---

Feel free to [contact us](/reference/contacts) if you have any question and collaborate with us on GitHub!
