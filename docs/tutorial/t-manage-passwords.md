> [Charmed MySQL Tutorial](/t/9922) > 4. Manage passwords

# Manage passwords

When we accessed MySQL earlier in this tutorial, we needed to use a password manually. Passwords help to secure our database and are essential for security. Over time, it is a good practice to change the password frequently. 

This section will go through setting and changing the password for the admin user.

## Summary
* [Retrieve the root password](#retrieve-the-root-password)
* [Rotate the root password](#rotate-the-root-password)
* [Set the root password](#set-the-root-password)

---

## Retrieve the root password
The root user's password can be retrieved by running the `get-password` action on the Charmed MySQL application:
```shell
juju run mysql/leader get-password
```
Example output:
```shell
...
password: yWJjs2HccOmqFMshyRcwWnjF
username: root
```

## Rotate the root password
You can change the root user's password to a new random password by running:
```shell
juju run mysql/leader set-password
```
Example output:
```shell
Running operation 12 with 1 task
  - task 13 on unit-mysql-1

Waiting for task 13...
status: completed
```
The `status: completed` above means the password has been successfully updated. To be sure, call `get-password` once again to check that the root password is different from the previous password.

## Set the root password
You can change the root password to a specific password by running:
```shell
juju run mysql/leader set-password password=my-password && \
juju run mysql/leader get-password
```
Example output:
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

> Next step: [5. Integrate with another application](/t/9916)