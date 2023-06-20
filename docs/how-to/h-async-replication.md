# Configuring asynchronous replication: MySQL InnoDB ClusterSet

> **WARNING**: it is an internal article. Do NOT use it in production! Contact [Canonical Data Platform team](https://chat.charmhub.io/charmhub/channels/data-platform) if you are interested in the topic.

## Intro
Read more about [MySQL InnoDB ClusterSet](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-clusterset.html) and watch the [presentation](https://videohub.oracle.com/media/Disaster+Recovery+with+MySQL+InnoDB+ClusterSet+-+What+is+it+and+how+do+I+use+itF/1_w0naxll1/170883371).

For simplicity, we deploy both MySQL InnoDB Clusters into the same model, but the proper design is to install them in different Regions/Clouds:

![MySQL_async_ClusterSet|690x586](upload://t8RCVAmkq1Hp5BwJM85ZJwxkREP.png) 

## Bootstrap
Bootstrap two MySQL InnoDB Clusters (Rome and Lisbon) and test application to generate SQL traffic:
```shell
juju deploy --constraints mem=2G mysql mysql-1st --channel 8.0/edge -n 3 --config cluster-name=ROME
juju deploy --constraints mem=2G mysql mysql-2nd --channel 8.0/edge -n 3 --config cluster-name=LISBON
juju deploy mysql-test-app --channel edge
juju relate mysql-1st mysql-test-app:database
juju wait-for application mysql-1st --query='status=="active"' && juju wait-for application mysql-2nd --query='status=="active"'
```
## Collect clusters details
Collect both clusters credentials to reuse later:
```shell
cluster_name_1st=$(juju show-unit mysql-1st/0 | yq '.. | select(. | has("cluster-name")).cluster-name')
cluster_name_2nd=$(juju show-unit mysql-2nd/0 | yq '.. | select(. | has("cluster-name")).cluster-name')
root_password_1st=$(juju run-action mysql-1st/0 get-password username=root --wait | yq '.. | select(. | has("password")).password')
root_password_2nd=$(juju run-action mysql-2nd/0 get-password username=root --wait | yq '.. | select(. | has("password")).password')
serverconfig_password_1st=$(juju run-action mysql-1st/0 get-password username=serverconfig --wait | yq '.. | select(. | has("password")).password')
serverconfig_password_2nd=$(juju run-action mysql-2nd/0 get-password username=serverconfig --wait | yq '.. | select(. | has("password")).password')
clusteradmin_password_1st=$(juju run-action mysql-1st/0 get-password username=clusteradmin --wait | yq '.. | select(. | has("password")).password')
clusteradmin_password_2nd=$(juju run-action mysql-2nd/0 get-password username=clusteradmin --wait | yq '.. | select(. | has("password")).password')

cat << EOF
Cluster names:
  1st: ${cluster_name_1st}
  2nd: ${cluster_name_2nd}
Credentials:
  1st: root:${root_password_1st}
  2nd: root:${root_password_2nd}
  1st: serverconfig:${serverconfig_password_1st}
  2nd: serverconfig:${serverconfig_password_2nd}
  1st: clusteradmin:${clusteradmin_password_1st}
  2nd: clusteradmin:${clusteradmin_password_2nd}
EOF
```

## Sync credentials
It is important to set the first cluster credentials on the second cluster to allow charm operator to continue managing 2nd Cluster after joining the ClusterSet:
```shell
juju run-action mysql-2nd/leader set-password username=root password=${root_password_1st} --wait # not really necessary.
juju run-action mysql-2nd/leader set-password username=clusteradmin password=${clusteradmin_password_1st} --wait
juju run-action mysql-2nd/leader set-password username=serverconfig password=${serverconfig_password_1st} --wait
```

## Destroy the 2nd Cluster (to be re-created inside the ClusterSet)
It is NOT possible to "merge" two different MySQL InnoDB Clusters due to [different GTID](https://dev.mysql.com/doc/mysql-shell/8.0/en/innodb-clusterset-rejoin.html) on both Clusters. We are going to dissolve the second Cluster to re-create it as a clone of the first one:
```shell
juju ssh mysql-2nd/leader charmed-mysql.mysqlsh --py -h127.0.0.1 -uclusteradmin -p${clusteradmin_password_1st}

> dba.get_cluster().dissolve() # answer YES to all questions, remember IPs of all cluster members
```

## Re-create the 2nd Cluster as 1st Cluster clone
Create the second cluster as a clone copy of the first cluster under the first ClusterSet.

**IMPORTANT**: replace all `FIXME_` labels with a proper values (unit IPs and cluster-name)!

```shell
juju ssh mysql-1st/leader charmed-mysql.mysqlsh --py -h127.0.0.1 -uclusteradmin -p${clusteradmin_password_1st}

> cs = dba.get_cluster_set()
> cluster2 = cs.create_replica_cluster("clusteradmin@FIXME_IP_1:3306", "FIXME_LISBON", recoveryProgress=1, timeout=10, recoveryMethod='clone')
> cluster2.add_instance('clusteradmin@FIXME_IP_2:3306', label="mysql-2nd-1")
> cluster2.add_instance('clusteradmin@FIXME_IP_3:3306', label="mysql-2nd-2")
```

## Check the status
Check the Juju and MySQL InnoDB Cluster(Set) statuses:
```shell
juju status

Model       Controller  Cloud/Region         Version  SLA          Timestamp
clusterset  lxd         localhost/localhost  2.9.43   unsupported  15:27:08+02:00

App             Version          Status  Scale  Charm           Channel   Rev  Exposed  Message
mysql-1st       8.0.32-0ubun...  active      3  mysql           8.0/edge  164  no       
mysql-2nd       8.0.32-0ubun...  active      3  mysql           8.0/edge  164  no       
mysql-test-app  0.0.2            active      1  mysql-test-app  edge       20  no       

Unit               Workload  Agent  Machine  Public address  Ports               Message
mysql-1st/0        active    idle   0        10.18.215.9     3306/tcp,33060/tcp  
mysql-1st/1        active    idle   1        10.18.215.81    3306/tcp,33060/tcp  
mysql-1st/2*       active    idle   2        10.18.215.67    3306/tcp,33060/tcp  Primary
mysql-2nd/0        active    idle   3        10.18.215.21    3306/tcp,33060/tcp  
mysql-2nd/1        active    idle   4        10.18.215.87    3306/tcp,33060/tcp  
mysql-2nd/2*       active    idle   5        10.18.215.60    3306/tcp,33060/tcp  Primary
mysql-test-app/0*  active    idle   6        10.18.215.174                       

Machine  State    Address        Inst id        Series  AZ  Message
0        started  10.18.215.9    juju-014b8f-0  jammy       Running
1        started  10.18.215.81   juju-014b8f-1  jammy       Running
2        started  10.18.215.67   juju-014b8f-2  jammy       Running
3        started  10.18.215.21   juju-014b8f-3  jammy       Running
4        started  10.18.215.87   juju-014b8f-4  jammy       Running
5        started  10.18.215.60   juju-014b8f-5  jammy       Running
6        started  10.18.215.174  juju-014b8f-6  jammy       Running
```

MySQL InnoDB ClusterSet status:
```shell
juju ssh mysql-1st/leader charmed-mysql.mysqlsh --py -h127.0.0.1 -uclusteradmin -p${clusteradmin_password_1st}

> dba.get_cluster_set().status(extended=1);
{
    "clusters": {
        "LISBON": {
            "clusterRole": "REPLICA", 
            "clusterSetReplication": {
                "applierStatus": "APPLIED_ALL", 
                "applierThreadState": "Waiting for an event from Coordinator", 
                "applierWorkerThreads": 4, 
                "receiver": "10.18.215.60:3306", 
                "receiverStatus": "ON", 
                "receiverThreadState": "Waiting for source to send event", 
                "source": "10.18.215.67:3306"
            }, 
            "clusterSetReplicationStatus": "OK", 
            "globalStatus": "OK", 
            "status": "OK", 
            "statusText": "Cluster is ONLINE and can tolerate up to ONE failure.", 
            "topology": {
                "10.18.215.21:3306": {
                    "address": "10.18.215.21:3306", 
                    "memberRole": "SECONDARY", 
                    "mode": "R/O", 
                    "replicationLagFromImmediateSource": "", 
                    "replicationLagFromOriginalSource": "", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }, 
                "10.18.215.60:3306": {
                    "address": "10.18.215.60:3306", 
                    "memberRole": "PRIMARY", 
                    "mode": "R/O", 
                    "replicationLagFromImmediateSource": "", 
                    "replicationLagFromOriginalSource": "", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }, 
                "mysql-2nd-1": {
                    "address": "10.18.215.87:3306", 
                    "memberRole": "SECONDARY", 
                    "mode": "R/O", 
                    "replicationLagFromImmediateSource": "", 
                    "replicationLagFromOriginalSource": "", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }
            }, 
            "transactionSet": "0a2d1861-0ea1-11ee-8ec2-00163ef59470:1-17047,0a2d1b28-0ea1-11ee-8ec2-00163ef59470:1-5,1549f330-0ea2-11ee-95a9-00163e5d863b:1-7,ec27d3f3-0ea0-11ee-aa9d-00163ef59470:1-4", 
            "transactionSetConsistencyStatus": "OK", 
            "transactionSetErrantGtidSet": "", 
            "transactionSetMissingGtidSet": ""
        }, 
        "ROME": {
            "clusterRole": "PRIMARY", 
            "globalStatus": "OK", 
            "primary": "10.18.215.67:3306", 
            "status": "OK", 
            "statusText": "Cluster is ONLINE and can tolerate up to ONE failure.", 
            "topology": {
                "mysql-1st-0": {
                    "address": "10.18.215.9:3306", 
                    "memberRole": "SECONDARY", 
                    "mode": "R/O", 
                    "replicationLagFromImmediateSource": "", 
                    "replicationLagFromOriginalSource": "", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }, 
                "mysql-1st-1": {
                    "address": "10.18.215.81:3306", 
                    "memberRole": "SECONDARY", 
                    "mode": "R/O", 
                    "replicationLagFromImmediateSource": "", 
                    "replicationLagFromOriginalSource": "", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }, 
                "mysql-1st-2": {
                    "address": "10.18.215.67:3306", 
                    "memberRole": "PRIMARY", 
                    "mode": "R/W", 
                    "status": "ONLINE", 
                    "version": "8.0.32"
                }
            }, 
            "transactionSet": "0a2d1861-0ea1-11ee-8ec2-00163ef59470:1-17047,0a2d1b28-0ea1-11ee-8ec2-00163ef59470:1-5,1549f330-0ea2-11ee-95a9-00163e5d863b:1-6,ec27d3f3-0ea0-11ee-aa9d-00163ef59470:1-4"
        }
    }, 
    "domainName": "cluster-set-0a16c7e0e4d4a8c8956911b8cadb17f3", 
    "globalPrimaryInstance": "10.18.215.67:3306", 
    "metadataServer": "10.18.215.67:3306", 
    "primaryCluster": "ROME", 
    "status": "HEALTHY", 
    "statusText": "All Clusters available."
}
 MySQL  127.0.0.1:33060+ ssl  Py > 
```

All OK here!

## MySQL Router
Removing test application to bootstrap two independent test applications behind mysql-router to provide the complete setup as displayed on the diagram above:
```shell
juju remove-application mysql-test-app
```
Bootstrap mysql-router with two independent test applications (note: `series` must match due to subordinate nature of `mysql-router`):
```shell
juju deploy mysql-test-app application-1st --channel edge --series jammy
juju deploy mysql-test-app application-2nd --channel edge --series jammy
juju deploy mysql-router mysql-router-1st --channel dpe/edge --series jammy
juju deploy mysql-router mysql-router-2nd --channel dpe/edge --series jammy

juju relate application-1st mysql-router-1st
juju relate mysql-router-1st mysql-1st # relate to primary ClusterSet first, otherwise cannot bootstrap!
juju relate mysql-router-1st mysql-2nd

juju relate application-2nd mysql-router-2nd
juju relate mysql-router-2nd mysql-1st # relate to primary ClusterSet first, otherwise cannot bootstrap!
juju relate mysql-router-2nd mysql-2nd
```

MySQL InnoDB ClusterSet configured MySQL Router automatically and test applications start using database:
```shell
juju ssh mysql-1st/leader charmed-mysql.mysqlsh --py -h127.0.0.1 -uclusteradmin -p${clusteradmin_password_1st}

> dba.get_cluster_set().list_routers()
{
    "domainName": "cluster-set-0a16c7e0e4d4a8c8956911b8cadb17f3", 
    "routers": {
        "juju-014b8f-10.lxd::application-2nd": {
            "hostname": "juju-014b8f-10.lxd", 
            "lastCheckIn": "2023-06-19 15:06:45", 
            "roPort": "3307", 
            "roXPort": "3309", 
            "rwPort": "3306", 
            "rwXPort": "3308", 
            "targetCluster": null, 
            "version": "8.0.32"
        }, 
        "juju-014b8f-9.lxd::application-1st": {
            "hostname": "juju-014b8f-9.lxd", 
            "lastCheckIn": "2023-06-19 14:58:35", 
            "roPort": "3307", 
            "roXPort": "3309", 
            "rwPort": "3306", 
            "rwXPort": "3308", 
            "targetCluster": null, 
            "version": "8.0.32"
        }
    }
}
```

Juju status shows all the necessary relation and happy:
```shell
> juju status --relations
Model       Controller  Cloud/Region         Version  SLA          Timestamp
clusterset  lxd         localhost/localhost  2.9.43   unsupported  17:25:07+02:00

App               Version          Status   Scale  Charm           Channel   Rev  Exposed  Message
application-1st   0.0.2            active       1  mysql-test-app  edge       20  no       
application-2nd   0.0.2            waiting      1  mysql-test-app  edge       20  no       
mysql-1st         8.0.32-0ubun...  active       3  mysql           8.0/edge  164  no       
mysql-2nd         8.0.32-0ubun...  active       3  mysql           8.0/edge  164  no       
mysql-router-1st                   active       1  mysql-router    dpe/edge   77  no       
mysql-router-2nd                   active       1  mysql-router    dpe/edge   77  no       

Unit                   Workload  Agent  Machine  Public address  Ports                                Message
application-1st/0*     active    idle   9        10.18.215.211                                        
  mysql-router-1st/0*  active    idle            10.18.215.211   6446/tcp,6447/tcp,6448/tcp,6449/tcp  
application-2nd/1*     waiting   idle   11       10.18.215.157                                        
  mysql-router-2nd/1*  active    idle            10.18.215.157   6446/tcp,6447/tcp,6448/tcp,6449/tcp  
mysql-1st/1            active    idle   1        10.18.215.81    3306/tcp,33060/tcp                   
mysql-1st/2*           active    idle   2        10.18.215.67    3306/tcp,33060/tcp                   Primary
mysql-1st/3            active    idle   8        10.18.215.86    3306/tcp,33060/tcp                   
mysql-2nd/0            active    idle   3        10.18.215.21    3306/tcp,33060/tcp                   
mysql-2nd/1            active    idle   4        10.18.215.87    3306/tcp,33060/tcp                   
mysql-2nd/2*           active    idle   5        10.18.215.60    3306/tcp,33060/tcp                   Primary

Machine  State    Address        Inst id         Series  AZ  Message
1        started  10.18.215.81   juju-014b8f-1   jammy       Running
2        started  10.18.215.67   juju-014b8f-2   jammy       Running
3        started  10.18.215.21   juju-014b8f-3   jammy       Running
4        started  10.18.215.87   juju-014b8f-4   jammy       Running
5        started  10.18.215.60   juju-014b8f-5   jammy       Running
8        started  10.18.215.86   juju-014b8f-8   jammy       Running
9        started  10.18.215.211  juju-014b8f-9   jammy       Running
11       started  10.18.215.157  juju-014b8f-11  jammy       Running

Relation provider                    Requirer                             Interface           Type         Message
application-1st:application-peers    application-1st:application-peers    application-peers   peer         
application-2nd:application-peers    application-2nd:application-peers    application-peers   peer         
mysql-1st:database                   mysql-router-1st:backend-database    mysql_client        regular      
mysql-1st:database                   mysql-router-2nd:backend-database    mysql_client        regular      
mysql-1st:database-peers             mysql-1st:database-peers             mysql_peers         peer         
mysql-2nd:database                   mysql-router-1st:backend-database    mysql_client        regular      
mysql-2nd:database                   mysql-router-2nd:backend-database    mysql_client        regular      
mysql-2nd:database-peers             mysql-2nd:database-peers             mysql_peers         peer         
mysql-router-1st:database            application-1st:database             mysql_client        subordinate  
mysql-router-1st:mysql-router-peers  mysql-router-1st:mysql-router-peers  mysql_router_peers  peer         
mysql-router-2nd:database            application-2nd:database             mysql_client        subordinate  
mysql-router-2nd:mysql-router-peers  mysql-router-2nd:mysql-router-peers  mysql_router_peers  peer         
```

## ClusterSet/Cluster Switchovers
to be continued...

## Appendix
 * [Jira Epic](https://warthogs.atlassian.net/browse/DPE-2147): [VM](https://warthogs.atlassian.net/browse/DPE-2148) and [K8s](https://warthogs.atlassian.net/browse/DPE-2149) cases.