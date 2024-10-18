# How to deploy using Terraform

[Terraform](https://www.terraform.io/) is an infrastructure automation tool to provision and manage resources in clouds or data centers. To deploy Charmed MySQL using Terraform and Juju, you can use the [Juju Terraform Provider](https://registry.terraform.io/providers/juju/juju/latest). 

The easiest way is to start from [these examples of terraform modules](https://github.com/canonical/terraform-modules) prepared by Canonical. This page will guide you through a deployment using an example module for MySQL on machines.

For an in-depth introduction to the Juju Terraform Provider, read [this Discourse post](https://discourse.charmhub.io/t/6939).

[note]
**Note**: Storage support was added in [Juju Terraform Provider version 0.13+](https://github.com/juju/terraform-provider-juju/releases/tag/v0.13.0).
[/note]

## Summary
* [Install Terraform tooling](#install-terraform-tooling)
* [Verify the deployment](#verify-the-deployment)
* [Apply the deployment](#apply-the-deployment)
* [Check deployment status](#check-deployment-status)
* [Clean up](#clean-up)
---

## Install Terraform tooling

This guide assumes Juju is installed and you have an LXD controller already bootstrapped. For more information, check the [Set up the environment](/t/9924) tutorial page.

Let's install Terraform Provider and example modules:
```shell
sudo snap install terraform --classic
```
Switch to the LXD provider and create a new model:
```shell
juju switch lxd
juju add-model my-model
```
Clone examples and navigate to the MySQL machine module:
```shell
git clone https://github.com/canonical/mysql-operator.git
cd mysql-operator/terraform
```

Initialise the Juju Terraform Provider:
```shell
terraform init
```

## Configure the deployment

The plan is fully configurable using the following variables:

| Name | Description | Type | Default | Required |
| - | - | - | - | - |
| `juju_model_name` | Name of the Juju model to deploy the application to | `string` | n/a | yes |
| `app_name` | Name of the application to deploy | `string` | `"mysql"` | no |
| `channel` | Charm channel to deploy the application from | `string` | `"8.0/stable"` | no |
| `revision` | Charm revision to deploy the application from, defaults to one in channel | `number` | null | no |
| `base` | Base image to deploy the application on | `string` | `"ubuntu@22.04"` | no |
| `units` | Number of units to deploy | `number` | `1` | no |
| `constraints` | Juju constraints to apply to the application | `string` | `"arch=amd64"` | no |
| `storage_size` | Size of the storage pool to create | `string` | `"10G"` | no |
| `config` | Charm configuration options. Configuration reference [here](https://charmhub.io/mysql/configurations) | `map(string)` | `{}` | no |


## Verify the deployment

Run `terraform plan` to get a preview of the changes that will be made:

```shell
terraform plan -var "juju_model_name=my-model"
```

## Apply the deployment

If everything looks correct, deploy the resources (skip the approval):

```shell
terraform apply -auto-approve -var "juju_model_name=my-model"
```

[note]
A machine controller with a `my-model` need to be in place before running the command.
[/note]


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
mysql  8.0.36-0ubun...  active      1  mysql  8.0/stable  240  no                                   

Unit      Workload  Agent  Machine  Public address  Ports           Message    
mysql/0*  active    idle   0        10.101.248.225  3306,33060/tcp  Primary                           

Machine  State    Address         Inst id        Base          AZ  Message
0        started  10.101.248.225  juju-c4a403-0  ubuntu@22.04      Running   
```

Continue to operate the charm as usual from here or apply further Terraform changes.

## Clean up

To keep the house clean, remove the newly deployed Charmed PostgreSQL by running
```shell
terraform destroy -var "juju_model_name=my-model"
```

Sample output:
```shell
juju_application.machine_mysql: Refreshing state... [id=my-model:mysql]

Terraform used the selected providers to generate the following execution plan. Resource actions are indicated with the following symbols:
  - destroy

Terraform will perform the following actions:

  # juju_application.machine_mysql will be destroyed
  - resource "juju_application" "machine_mysql" {
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
              - size  = "99G" -> null
            },
        ] -> null
      - trust       = true -> null
      - units       = 1 -> null

      - charm {
          - base     = "ubuntu@22.04" -> null
          - channel  = "8.0/stable" -> null
          - name     = "mysql" -> null
          - revision = 240 -> null
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

juju_application.machine_mysql: Destroying... [id=my-model:mysql]
juju_application.machine_mysql: Destruction complete after 0s

Destroy complete! Resources: 1 destroyed.
```

## Sourcing MySQL charm terraform module

To use the MySQL charm terraform module in your own solution, one can source and configure the module like:

```hcl
module "mysql" {
  source          = "git::https://github.com/canonical/mysql-operator//terraform?ref=main"
  juju_model_name = "my-model"
  channel         = "8.0/stable"
  revision        = 240
  config          = "{profile="testing", binlog_retention_days=3 }"
  storage_size    = "20G"
  units           = 3
  constraints     = "arch=amd64"
}
```

---
[note]
For more examples of Terraform modules for VM, see the other directories in the [`terraform-modules` repository](https://github.com/canonical/terraform-modules/tree/main/modules/machine).
[/note]

Feel free to [contact us](/t/11867) if you have any question and [collaborate with us on GitHub](https://github.com/canonical/terraform-modules)!