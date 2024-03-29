# Enable Security in your MySQL deployment 
> **:information_source: Hint**: Use [Juju 3](/t/5064). Otherwise replace `juju integrate ...` with `juju relate ...` for Juju 2.9.

This is part of the [Charmed MySQL Tutorial](/t/9922). Please refer to this page for more information and the overview of the content.

## Transport Layer Security (TLS)
[TLS](https://en.wikipedia.org/wiki/Transport_Layer_Security) is used to encrypt data exchanged between two applications; it secures data transmitted over the network. Typically, enabling TLS within a highly available database, and between a highly available database and client/server applications, requires domain-specific knowledge and a high level of expertise. Fortunately, the domain-specific knowledge has been encoded into Charmed MySQL. This means (re-)configuring TLS on Charmed MySQL is readily available and requires minimal effort on your end.

The production ready [TLS Certificates Charm](https://charmhub.io/tls-certificates-operator) is available on [CharmHub](http://charmhub.io/). It centralizes TLS certificate management in a consistent manner and handles providing, requesting, and renewing TLS certificates. As for the tutorial purpose, we will choose simplified analogue [Self Signed Certificates](https://charmhub.io/self-signed-certificates). Again, relations come in handy here as TLS is enabled via relations; i.e. by relating Charmed MySQL to the "Self Signed Certificates" charm. 

### Configure TLS
Before enabling TLS on Charmed MySQL we must first deploy the `self-signed-certificates` charm:
```shell
juju deploy self-signed-certificates --channel edge
```

Wait until the `self-signed-certificates` is up and active, use `juju status --watch 1s` to monitor the progress:
```shell
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  2.9.42   unsupported  00:40:42+01:00

App                        Version          Status  Scale  Charm                      Channel     Rev  Exposed  Message
mysql                      8.0.32-0ubun...  active      2  mysql                      8.0/stable  147  no
self-signed-certificates                    active      1  self-signed-certificates   edge        27   no

Unit                          Workload  Agent  Machine  Public address  Ports  Message
mysql/0*                      active    idle   0        10.234.188.135         Primary
mysql/1                       active    idle   1        10.234.188.214
self-signed-certificates/1*   active    idle   6        10.234.188.19

Machine  State    Address         Inst id        Series  AZ  Message
0        started  10.234.188.135  juju-ff9064-0  jammy       Running
1        started  10.234.188.214  juju-ff9064-1  jammy       Running
6        started  10.234.188.19   juju-ff9064-6  focal       Running
```
*Note: this tutorial uses [self-signed certificates](https://en.wikipedia.org/wiki/Self-signed_certificate); self-signed certificates should not be used in a production cluster.*

### Add external TLS certificate
To enable TLS on Charmed MySQL, integrate the two applications:
```shell
juju integrate mysql self-signed-certificates
```

#### Check the TLS certificate in use:
Use `openssl` to connect to the MySQL and check the TLS certificate in use:
```shell
> openssl s_client -starttls mysql -connect 10.234.188.135:3306 | grep Issuer
...
depth=1 C = US, CN = self-signed-certificates-operator
...
```
Congratulations! MySQL is now using TLS certificate generated by the external application `self-signed-certificates`.


### Remove external TLS certificate
To remove the external TLS and return to the locally generate one, unrelate applications:
```shell
juju remove-relation mysql self-signed-certificates
```

#### Check the TLS certificate in use:
```shell
> openssl s_client -starttls mysql -connect 10.234.188.135:3306 | grep Issuer
```
The output should be similar to:
```shell
...
depth=1 CN = MySQL_Server_8.0.32_Auto_Generated_CA_Certificate
...
```
The Charmed MySQL application reverted to the placeholder certificate that was created locally during the MySQL server installation.