# Manage Passwords

This is part of the [Charmed MySQL Tutorial](/t/charmed-mysql-tutorial-overview/9922?channel=8/edge). Please refer to this page for more information and the overview of the content.

## Passwords
When we accessed MySQL earlier in this tutorial, we needed to use a password manually. Passwords help to secure our database and are essential for security. Over time it is a good practice to change the password frequently. Here we will go through setting and changing the password for the admin user.

### Retrieve the root password
As previously mentioned, the root password can be retrieved by running the `get-password` action on the Charmed MySQL application:
```shell
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "6"
  results:
    password: <password>
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:48:44 +0000 UTC
    enqueued: 2023-01-29 22:48:39 +0000 UTC
    started: 2023-01-29 22:48:43 +0000 UTC
```

### Rotate the root password
You can change the root password to a new random password by entering:
```shell
juju run-action mysql/leader set-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "14"
  results: {}
  status: completed
  timing:
    completed: 2023-01-29 22:50:45 +0000 UTC
    enqueued: 2023-01-29 22:50:42 +0000 UTC
    started: 2023-01-29 22:50:44 +0000 UTC
```
Please notice the `status: completed` above which means the password has been successfully updated. To be sure, please call `get-password` once again:
```shell
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "16"
  results:
    password: <new password>
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:50:50 +0000 UTC
    enqueued: 2023-01-29 22:50:49 +0000 UTC
    started: 2023-01-29 22:50:50 +0000 UTC
```
The root password should be different from the previous password.

### Set the root password
You can change the root password to a specific password by entering:
```shell
juju run-action mysql/leader set-password password=my-password --wait && \
juju run-action mysql/leader get-password --wait
```
Running the command should output:
```yaml
unit-mysql-0:
  UnitId: mysql/0
  id: "24"
  results: {}
  status: completed
  timing:
    completed: 2023-01-29 22:56:15 +0000 UTC
    enqueued: 2023-01-29 22:56:11 +0000 UTC
    started: 2023-01-29 22:56:14 +0000 UTC
unit-mysql-0:
  UnitId: mysql/0
  id: "26"
  results:
    password: my-password
    username: root
  status: completed
  timing:
    completed: 2023-01-29 22:56:16 +0000 UTC
    enqueued: 2023-01-29 22:56:15 +0000 UTC
    started: 2023-01-29 22:56:15 +0000 UTC
```
The root `password` should match whatever you passed in when you entered the command.