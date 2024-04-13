# Deploy Charmed MySQL on MAAS
[note type="negative"]
Warning: at the moment, known blocking issues for MAAS deployment: [GH-336](https://github.com/canonical/mysql-operator/issues/366)
[/note]

To deploy **MAAS for production** usage, follow [the official MAAS documentation](https://maas.io/docs/tutorial-bootstrapping-maas) and [Charmed MySQL tutorial](/t/9922).

This **playground deployment** based on the [Multipass-based blueprint instruction](https://discourse.maas.io/t/5360) (assuming Ubuntu 22.04 LTS is in use).

# Summary
 * Bootstrap isolated VM for playground
 * Install MAAS inside VM using cloud-init blueprint
 * Configure MAAS
 * Install and bootstrap Juju
 * Register MAAS as a new cloud on Juju
 * Deploy Charmed MySQL on MAAS using Juju
 * Test Charmed MySQL deployment
 * Remove playground VM to keep the house clean

# Bootstrap the new Multipass VM with pre-installed MAAS
```shell
sudo snap install multipass

wget -qO- https://raw.githubusercontent.com/canonical/maas-multipass/main/maas.yml \
 | multipass launch --name maas -c8 -m12GB -d50GB --cloud-init -

multipass ls
> maas     Running    10.76.203.138    Ubuntu 22.04 LTS
>                     10.10.10.1
# note: YOUR_MAAS_IP for further use is 10.76.203.138 

multipass shell maas
```
# Configure MAAS and dump credentials for Juju:
 * Open http://YOUR_MAAS_IP:5240/MAAS/ and finish MAAS initial configuration: add DNS IPs, pull your SSH keys from GH/Launchpad, ... (MAAS WEB default login/pass: admin/admin).

 * Wait for images download completed on http://YOUR_MAAS_IP:5240/MAAS/r/images
![Screenshot from 2024-04-12 12-48-40|690x228](upload://kyNPhsHr7GHyFouEpp7sxPytb6g.png)

    Note: Make sure you are downloading 22.04 images as well (20.04 is the current default).

* add tag `juju` on http://YOUR_MAAS_IP:5240/MAAS/r/tags (just create new tag with tag-name=juju, all other options keep default)

* assign newly created tag to already available pre-created LXD machine:
![Screenshot from 2024-04-12 12-51-30|690x299](upload://44dY32yFYSybmvypdEgDtj0lFid.png)
  Note: the LXD machine will be up and running after the images downloading and sync is completed!

 * MAAS uses DHCP to boot/install new machines. Enable DHCP manually if you see this banner on each MAAS page:
![image|690x46](upload://g458TLPPqGIISCFHKdfUwXRepeZ.png)
  Note: enable DHCP service inside MAAS VM only! Use internal VM network `fabric-1` on `10.10.10.0/24`, choose a range you want, e.g. `10.10.10.100-10.10.10.120`. Follow [the official MAAS manual](https://maas.io/docs/enabling-dhcp)!

 * Dump MAAS admin user API key to add as a Juju credentials later:
```
sudo maas apikey --username admin
```

# Install Juju into Multipass VM

NOTE: Make sure you are inside Multipass VM: `multipass shell maas` !

```shell
sudo snap install juju
sudo snap install jhack --channel edge
```

# Add MAAS cloud and credentials into Juju
```shell
juju add-cloud
> Since Juju 2 is being run for the first time, downloading latest cloud information. Fetching latest public cloud list... Your list of public clouds is up to date, see `juju clouds`. Cloud Types
>    maas
>    manual
>    openstack
>    oracle
>    vsphere
> 
> Select cloud type: maas
> Enter a name for your maas cloud: maas-cloud 
> Enter the API endpoint url: http://YOUR_MAAS_IP:5240/MAAS
> Cloud "maas-cloud" 

juju add-credential maas-cloud 
> ...
> Enter credential name: maas-credentials
> 
> Regions
>   default
> Select region [any region, credential is not region specific]: default
> ...
> Using auth-type "oauth1". 
> Enter maas-oauth: $(paste the MAAS Keys copied from the output above or from http://YOUR_MAAS_IP:5240/MAAS/r/account/prefs/api-keys ) 
> Credential "maas-credentials" added locally for cloud "maas-cloud".
```

# Bootstrap Juju
Note: use `--credential` if you regestered several MAAS credentials and `--debug` option if you want to see bootstrap details.
```shell
juju bootstrap --constraints tags=juju maas-cloud maas-controller # --credential maas-credentials --debug
```

# Deploy Charmed MySQL on MAAS using Juju
```shell
juju add-model mysql
juju deploy mysql --channel 8.0/stable
juju status --watch 1s
```

The expected result:
```shell
TODO
```

# Test your Charmed MySQL deployment

Check the [Testing](/t/11770) reference to test your deployment.

# Clean your playground

Above, we have successfully deployed Charmed MySQL on MAAS, but it is important to keep the house clean.  To stop your VM, execute: 
```shell
multipass stop maas
```
If you're done with testing and would like to free up resources on your machine, you can remove the VM entirely.

[note type="negative"]
**Warning**: When you remove VM as shown below, you will lose all the data in MySQL and any other applications inside Multipass VM! 

For more information, see the docs for [`multipass delete`](https://multipass.run/docs/delete-command).
[/note]

To delete your VM and its data, run:
```shell
multipass delete --purge maas
```