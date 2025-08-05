
# How to enable TLS encryption

```{note}
**Note**: All commands are written for `juju >= v.3.1`

If you're using `juju 2.9`, check the [`juju 3.0` Release Notes](https://juju.is/docs/juju/roadmap#juju-3-0-0---22-oct-2022).
```
This guide will show how to enable TLS using the [`self-signed-certificates` operator](https://github.com/canonical/self-signed-certificates-operator) as an example.

```{caution}
**[Self-signed certificates](https://en.wikipedia.org/wiki/Self-signed_certificate) are not recommended for a production environment.**

Check [this guide](https://discourse.charmhub.io/t/11664) for an overview of the TLS certificates charms available. 
```


## Enable TLS

First, deploy the TLS charm:
```shell
juju deploy self-signed-certificates
```
To enable TLS, integrate the two applications:
```shell
juju integrate self-signed-certificates mysql
```

## Manage keys

Updates to private keys for certificate signing requests (CSR) can be made via the `set-tls-private-key` action. Note that passing keys to external/internal keys should *only be done with* `base64 -w0`, *not* `cat`.

With three replicas, this schema should be followed:

Generate a shared internal (private) key
```shell
openssl genrsa -out internal-key.pem 3072
```

Apply the newly generated internal key on each `juju` unit:
```shell
juju run mysql/0 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run mysql/1 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run mysql/2 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
```

Updates can also be done with auto-generated keys:
```shell
juju run mysql/0 set-tls-private-key
juju run mysql/1 set-tls-private-key
juju run mysql/2 set-tls-private-key
```

## Disable TLS
Disable TLS by removing the integration:
```shell
juju remove-relation self-signed-certificates mysql
```

