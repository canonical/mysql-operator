
# Deploy in an offline or air-gapped environment

An air-gapped environment refers to a system that does not have access to the public internet.
This guide goes through the special configuration steps for installing Charmed MySQL VM in an air-gapped environment.

## Requirements

Canonical does not prescribe how you should set up your specific air-gapped environment. However, it is assumed that it meets the following conditions:

* A VM/hardware resources available for Juju.
* DNS is configured to the local nameservers.
* [Juju is configured](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#configure-juju) to use local air-gapped services.
* The [`store-admin`](https://snapcraft.io/store-admin) tool is installed and configured.
* [Air-gapped CharmHub](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub) is installed and running.
* [Air-gapped Snap Store Proxy](https://documentation.ubuntu.com/snap-store-proxy/) is installed and running.
* Local APT and LXD Images caches are reachable.

## Air-gapped setup summary

[1\. Export snaps and charms](1-export-snaps-and-charms) <br>
[2\. Transfer binary blobs](2-transfer-the-binary-blobs) <br>
[3\. Import snaps and charms](3-import-snaps-and-charms) <br>
[4\. Deploy MySQL](4-deploy-mysql)

## Air-gapped day-to-day example

(1-export-snaps-and-charms)=
### 1. Export snaps and charms
Exporting VM SNAPs and Charms and  are currently independent processes. The `store-admin` tool is designed to simplify the process. 

Future improvements are planned to the `store-admin` tool so that it could potentially export all necessary SNAP resource(s) from the official SnapStore with Charms simultaneously. Other planned improvements include supporting the export of specific charm and resource by revisions ([PF-5369](https://warthogs.atlassian.net/browse/PF-5369), [PF-5185](https://warthogs.atlassian.net/browse/PF-5185)).

#### Charms
 The necessary charm(s) can be exported as bundle or independently (charm-by-charm). See the Snap Proxy documentation:
* [Offline Charmhub configuration > Export charm bundle](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#export-charm-bundles)
* [Offline Charmhub configuration > Export charms](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#export-charms)

The bundle export example:

<details> 
<summary><code>store-admin export bundle mysql-bundle --channel=8.0/edge --series=jammy --arch=amd64</code></summary>

```
Downloading mysql-bundle revision 52 (8.0/edge)
  [####################################]  100%
Downloading data-integrator revision 71 (edge)
  [####################################]  100%
Downloading grafana-agent revision 286 (edge)
  [####################################]  100%          
Downloading landscape-client revision 69 (edge)
  [####################################]  100%          
Downloading mysql revision 301 (8.0/edge)
  [####################################]  100%          
Downloading mysql-router revision 247 (dpe/edge)
  [####################################]  100%          
Downloading mysql-test-app revision 63 (edge)
  [####################################]  100%          
Downloading s3-integrator revision 59 (edge)
  [####################################]  100%
Downloading self-signed-certificates revision 200 (edge)
  [####################################]  100%          
Downloading sysbench revision 78 (edge)
  [####################################]  100%          
Downloading ubuntu-advantage revision 113 (edge)
  [####################################]  100%          
Successfully exported charm bundle mysql-bundle: /home/ubuntu/snap/store-admin/common/export/mysql-bundle-20241008T084100.tar.gz
```
</details>

#### SNAPs
Usually charms require SNAPs (and some manually pin them). For the manual SNAP exports, follow the official Snap Store Proxy documentation: [Offline Charmhub configuration > Export SNAP](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#export-snap-resources). Data team is shipping the mapping [snap.yaml](https://github.com/canonical/mysql-bundle/blob/main/releases/latest/) to the published [bundle.yaml](https://github.com/canonical/mysql-bundle/blob/main/releases/latest/):

> **Warning**: always use snap.yaml and bundle.yaml from the same Git commit (to match each other)!

<details>
<summary><code>store-admin export snaps --from-yaml snaps.yaml</code></summary>

```shell
Downloading grafana-agent revision 51 (latest/stable amd64)
  [####################################]  100%          
Downloading grafana-agent revision 82 (latest/stable amd64)
  [####################################]  100%          
Downloading charmed-mysql revision 109 (8.0/edge amd64)
  [####################################]  100%          
Downloading charmed-mysql revision 114 (8.0/edge amd64)
  [####################################]  100%          
Downloading canonical-livepatch revision 282 (latest/stable amd64)
  [####################################]  100%          
Successfully exported snaps:
grafana-agent: /home/ubuntu/snap/store-admin/common/export/grafana-agent-20241008T082122.tar.gz
charmed-mysql: /home/ubuntu/snap/store-admin/common/export/charmed-mysql-20241008T082122.tar.gz
canonical-livepatch: /home/ubuntu/snap/store-admin/common/export/canonical-livepatch-20241008T082122.tar.gz
```
</details>

(2-transfer-the-binary-blobs)=
### 2. Transfer the binary blobs 

Transfer the binary blobs using the way of your choice into the air-gapped environment.

```shell
cp /home/ubuntu/snap/store-admin/common/export/*.tar.gz /media/usb/

...
cp /media/usb/*.tar.gz /var/snap/snap-store-proxy/common/charms-to-push/
```
> **Note**: always check [checksum](https://en.wikipedia.org/wiki/Checksum) for the transferred blobs!

(3-import-snaps-and-charms)=
### 3. Import snaps and charms

 Import the [snap](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap/#importing-pushing-snaps) and [charm](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#import-packages) blobs into local air-gapped CharmHub:

> **Note**: when importing machine charms that depend on a snap for functionality, you must first manually import the required snap.
```shell
sudo snap-store-proxy push-snap /var/snap/snap-store-proxy/common/snaps-to-push/charmed-mysql-20241008T082122.tar.gz

sudo snap-store-proxy push-charm-bundle /var/snap/snap-store-proxy/common/charms-to-push/mysql-bundle-20241003T104903.tar.gz
```
> **Note**: when [re-importing](https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub/#import-packages) charms or importing other revisions, make sure to provide the `--push-channel-map`.

(4-deploy-mysql)=
### 4. Deploy MySQL

 Deploy and operate Juju charms normally:
```shell
juju deploy mysql
```
```{note}
**Note**: All the charms revisions and snap revisions deployed in the air-gapped environment must match the official CharmHub and SnapStore revisions.

Use [the official release notes](/reference/releases) as a reference.
```

## Additional resources

* https://docs.ubuntu.com/snap-store-proxy/en/airgap
* https://documentation.ubuntu.com/snap-store-proxy/
* https://documentation.ubuntu.com/enterprise-store/main/how-to/airgap-charmhub
* https://ubuntu.com/kubernetes/docs/install-offline
* [Charmed Kubeflow > Install in an air-gapped environment](https://documentation.ubuntu.com/charmed-kubeflow/how-to/install/install-air-gapped/)
*  [Wikipedia > Air gap (networking)](https://en.wikipedia.org/wiki/Air_gap_(networking))

