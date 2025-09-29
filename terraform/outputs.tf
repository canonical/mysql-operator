output "app_name" {
  description = "Name of the MySQL Server VM application"
  value       = juju_application.mysql_server.name
}

output "provides" {
  description = "Map of all the provided endpoints"
  value = {
    database  = "database",
    cos_agent = "cos-agent",
  }
}

output "requires" {
  description = "Map of all the required endpoints"
  value = {
    certificates  = "certificates"
    s3_parameters = "s3-parameters"
    tracing       = "tracing"
  }
}
