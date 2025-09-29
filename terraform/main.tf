resource "juju_application" "mysql_server" {
  name  = var.app_name
  model = var.model_name

  charm {
    name     = "mysql"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }

  storage_directives = {
    database = var.storage_size
  }

  config            = var.config
  constraints       = var.constraints
  endpoint_bindings = var.endpoint_bindings
  units             = var.units
}
