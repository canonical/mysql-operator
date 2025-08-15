# How to connect to your database outside the local network

This page summarises resources for setting up deployments where an external application must connect to a MySQL database from outside the local area network.

## External application (non-Juju)

**Use case**: the client application is a non-Juju application outside of Juju / DB LAN.

There are many possible ways to connect the Charmed MySQL database from outside of the LAN the DB cluster is located. The available options are heavily depend on the cloud/hardware/virtualization in use. One of the possible options is to use [virtual IP addresses (VIP)](https://en.wikipedia.org/wiki/Virtual_IP_address) which the charm MySQL Router provides with assist of the charm/interface `hacluster`. Please follow the [MySQL Router documentation](https://charmhub.io/mysql-router/docs/h-external-access?channel=dpe/candidate) for such configuration.

## External relation (Juju)

**Use case**: the client application is a Juju application outside of DB deployment (e.g. hybrid Juju deployment with different VM clouds/controllers).

In this case the the cross-controllers-relation is necessary. Please [contact](/reference/contacts) the Data team to discuss the possible option for your use case.

