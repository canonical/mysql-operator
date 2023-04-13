# How to enable encryption

Note: The TLS settings here are for self-signed-certificates which are not recommended for production clusters, the `tls-certificates-operator` charm offers a variety of configurations, read more on the TLS charm [here](https://charmhub.io/tls-certificates-operator)

## Enable TLS

```shell
# deploy the TLS charm
juju deploy tls-certificates-operator
# add the necessary configurations for TLS
juju config tls-certificates-operator generate-self-signed-certificates="true" ca-common-name="Test CA"
# to enable TLS relate the two applications
juju relate tls-certificates-operator mysql
```

## Manage keys

Updates to private keys for certificate signing requests (CSR) can be made via the `set-tls-private-key` action. Note: passing the key should *only be done with* `base64 -w0` *not* `cat`. With three units this schema should be followed:

* Generate a shared internal (private) key

```shell
openssl genrsa -out internal-key.pem 3072
```

* apply newly generated internal key on juju leader:

```
juju run-action mysql/0 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)" --wait
juju run-action mysql/1 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)" --wait
juju run-action mysql/2 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)" --wait
```

* updates can also be done with auto-generated keys with

```
juju run-action mysql/0 set-tls-private-key --wait
juju run-action mysql/1 set-tls-private-key --wait
juju run-action mysql/2 set-tls-private-key --wait
```

## Disable TLS remove the relation
```shell
juju remove-relation tls-certificates-operator mysql
```