# How to enable encryption
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` and `juju integrate` with `juju relate` for Juju 2.9.

> **:warning: Warning**: The document uses '[self-signed-certificates](https://charmhub.io/self-signed-certificates)' which is NOT recommended for production clusters, the '[tls-certificates-operator](https://charmhub.io/tls-certificates-operator)' should be considered for production!

## Enable TLS

```shell
# deploy the TLS charm
juju deploy self-signed-certificates --channel edge

# to enable TLS relate the two applications
juju integrate self-signed-certificates mysql
```

## Manage keys

Updates to private keys for certificate signing requests (CSR) can be made via the `set-tls-private-key` action. Note: passing the key should *only be done with* `base64 -w0` *not* `cat`. With three units this schema should be followed:

* Generate a shared internal (private) key

```shell
openssl genrsa -out internal-key.pem 3072
```

* apply newly generated internal key on each juju unit:

```shell
juju run mysql/0 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run mysql/1 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run mysql/2 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
```

* updates can also be done with auto-generated keys with

```shell
juju run mysql/0 set-tls-private-key
juju run mysql/1 set-tls-private-key
juju run mysql/2 set-tls-private-key
```

## Disable TLS remove the relation
```shell
juju remove-relation self-signed-certificates mysql
```