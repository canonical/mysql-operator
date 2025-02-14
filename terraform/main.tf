resource "juju_application" "machine_mysql" {
  name  = var.app_name
  model = var.juju_model_name

  charm {
    name     = "mysql"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  storage_directives = {
    database = var.storage_size
  }

  units       = var.units
  constraints = var.constraints
  config      = var.config
}
