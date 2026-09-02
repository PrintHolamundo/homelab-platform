# ==============================================================================
# Container Identification Outputs
# ==============================================================================

output "container_id" {
  description = "The VM/LXC ID assigned to the container"
  value       = proxmox_virtual_environment_container.docker_ct.vm_id
}

output "container_hostname" {
  description = "The hostname configured for the container"
  value       = var.container_hostname
}

output "target_node" {
  description = "Proxmox node hosting the container"
  value       = var.target_node
}

# ==============================================================================
# Network & Access Outputs
# ==============================================================================

output "container_ip_cidr" {
  description = "Assigned IPv4 address with CIDR mask"
  value       = var.ipv4_address
}

output "container_ip" {
  description = "Assigned IPv4 address without CIDR mask"
  value       = split("/", var.ipv4_address)[0]
}

output "ssh_connection_command" {
  description = "Ready-to-use SSH connection command"
  value       = "ssh root@${split("/", var.ipv4_address)[0]}"
}