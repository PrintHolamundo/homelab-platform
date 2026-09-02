resource "proxmox_virtual_environment_container" "docker_ct" {
  description  = var.container_description
  node_name    = var.target_node
  vm_id        = var.container_id
  unprivileged = var.unprivileged

  initialization {
    hostname = var.container_hostname

    ip_config {
      ipv4 {
        address = var.ipv4_address
        gateway = var.ipv4_gateway
      }
    }

    user_account {
      keys = [
        trimspace(file(pathexpand(var.ssh_public_key_path)))
      ]
    }
  }

  network_interface {
    name = "veth0"
  }

  operating_system {
    template_file_id = var.template_file_id
    type             = "debian"
  }

  cpu {
    cores = var.cpu_cores
  }

  memory {
    dedicated = var.memory_dedicated
    swap      = var.memory_swap
  }

  disk {
    datastore_id = var.disk_datastore_id
    size         = var.disk_size
  }
  
  dynamic "mount_point" {
    for_each = var.mount_points
    content {
      volume    = mount_point.value.volume
      path      = mount_point.value.path
      read_only = mount_point.value.read_only
    }
  }

  features {
    nesting = true
    keyctl  = true
  }
}

resource "local_file" "ansible_inventory" {
  depends_on = [proxmox_virtual_environment_container.docker_ct]

  content = templatefile("${path.module}/templates/inventory.tftpl", {
    hostname        = var.container_hostname
    ip              = split("/", var.ipv4_address)[0]
    ssh_private_key = replace(var.ssh_public_key_path, ".pub", "")
  })

  filename = "${path.module}/../ansible-proxmox/inventory.ini"
}