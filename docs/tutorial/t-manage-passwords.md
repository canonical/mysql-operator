# Manage Passwords
> **:information_source: Note**: Use [Juju 3](/t/5064). Otherwise replace `juju run ...` with `juju run-action --wait ...` for Juju 2.9.

This is part of the [Charmed MySQL Tutorial](/t/9922). Please refer to this page for more information and the overview of the content.

## Passwords
When we accessed MySQL earlier in this tutorial, we needed to use a password manually. Passwords help to secure our database and are essential for security. Over time it is a good practice to change the password frequently. Here we will go through setting and changing the password for the admin user.

### Retrieve the root password
As previously mentioned, the root password can be retrieved by running the `get-password` action on the Charmed MySQL application:
```shell
juju run mysql/leader get-password
```
Running the command should output:
```shell
...
password: yWJjs2HccOmqFMshyRcwWnjF
username: root
```

### Rotate the root password
You can change the root password to a new random password by entering:
```shell
juju run mysql/leader set-password
```
Running the command should output:
```shell
Running operation 12 with 1 task
  - task 13 on unit-mysql-1

Waiting for task 13...
status: completed
```
Please notice the `status: completed` above which means the password has been successfully updated. To be sure, please call `get-password` once again:
```shell
juju run mysql/leader get-password
```
Running the command should output:
```shell
password: 5wEFCr67qMAmsbi0dcLGwvN9
username: root
```
The root password should be different from the previous password.

### Set the root password
You can change the root password to a specific password by entering:
```shell
juju run mysql/leader set-password password=my-password && \
juju run mysql/leader get-password
```
Running the command should output:
```shell
Running operation 18 with 1 task
  - task 19 on unit-mysql-1

Waiting for task 19...
Running operation 20 with 1 task
  - task 21 on unit-mysql-1

Waiting for task 21...
password: my-password
username: root
```
The root `password` should match whatever you passed in when you entered the command.