# Cleanup and extra info

This is part of the [Charmed MySQL Tutorial](/t/charmed-mysql-tutorial-overview/9922?channel=8/edge). Please refer to this page for more information and the overview of the content.

## Remove Multipass VM
If you're done with testing and would like to free up resources on your machine, just remove Multipass VM.
*Warning: when you remove VM as shown below you will lose all the data in MySQL and any other applications inside Multipass VM!*
```shell
multipass delete --purge my-vm
```

## Next Steps
In this tutorial we've successfully deployed MySQL, added/removed cluster members, added/removed users to/from the database, and even enabled and disabled TLS. You may now keep your Charmed MySQL deployment running and write to the database or remove it entirely using the steps in [Remove Charmed MySQL and Juju](#remove-charmed-mysql-and-juju). If you're looking for what to do next you can:
- Run [Charmed MySQL on Kubernetes](https://github.com/canonical/mysql-k8s-operator).
- Check out our Charmed offerings of [PostgreSQL](https://charmhub.io/postgresql?channel=edge) and [Kafka](https://charmhub.io/kafka?channel=edge).
- Read about [High Availability Best Practices](https://canonical.com/blog/database-high-availability)
- [Report](https://github.com/canonical/mysql-operator/issues) any problems you encountered.
- [Give us your feedback](https://chat.charmhub.io/charmhub/channels/data-platform).
- [Contribute to the code base](https://github.com/canonical/mysql-operator)
