# Charmed MySQL tutorial

The Charmed MySQL Operator delivers automated operations management from [day 0 to day 2](https://codilime.com/blog/day-0-day-1-day-2-the-software-lifecycle-in-the-cloud-age/) on the [MySQL Community Edition](https://www.mysql.com/products/community/) relational database. It is an open source, end-to-end, production-ready data platform [on top of Juju](https://juju.is/). As a first step this tutorial shows you how to get Charmed MySQL up and running, but the tutorial does not stop there. Through this tutorial you will learn a variety of operations, everything from adding replicas to advanced operations such as enabling Transport Layer Security (TLS). In this tutorial we will walk through how to:
- Set up your environment using LXD and Juju.
- Deploy MySQL using a single command.
- Access the admin database directly.
- Add high availability with MySQL InnoDB Cluster, Group Replication.
- Request and change the admin password.
- Automatically create MySQL users via Juju relations.
- Reconfigure TLS certificate in one command.

While this tutorial intends to guide and teach you as you deploy Charmed MySQL, it will be most beneficial if you already have a familiarity with:
- Basic terminal commands.
- MySQL concepts such as replication and users.

## Step-by-step guide

Here’s an overview of the steps required with links to our separate tutorials that deal with each individual step:
* [Set up the environment](/t/charmed-mysql-tutorial-setup-environment/9924?channel=8/edge)
* [Deploy PostgreSQL](/t/charmed-mysql-tutorial-deploy-mysql/9912?channel=8/edge)
* [Managing your units](/t/charmed-mysql-tutorial-managing-units/9920?channel=8/edge)
* [Manage passwords](/t/charmed-mysql-tutorial-manage-passwords/9918?channel=8/edge)
* [Relate your PostgreSQL to other applications](/t/charmed-mysql-tutorial-integrations/9916?channel=8/edge)
* [Enable security](/t/charmed-mysql-tutorial-enable-security/9914?channel=8/edge)
* [Cleanup your environment](/t/charmed-mysql-tutorial-cleanup-environment/9910?channel=8/edge)
