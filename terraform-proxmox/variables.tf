# ==============================================================================
# Proxmox Provider & Connection Settings
# ==============================================================================

variable "proxmox_endpoint" {
  type        = string
  description = "Base URL for the Proxmox API (e.g., https://192.168.1.100:8006/)"
}

variable "proxmox_username" {
  type        = string
  description = "Proxmox authentication username"
  default     = "root@pam"
}

variable "proxmox_password" {
  type        = string
  description = "Proxmox authentication password"
  sensitive   = true
}

# ==============================================================================
# Target Node & Access
# ==============================================================================

variable "target_node" {
  type        = string
  description = "Proxmox node name"
  default     = "pve"
}

variable "ssh_public_key_path" {
  type        = string
  description = "Path to the public SSH key"
  default     = "~/.ssh/id_ed25519.pub"
}

# ==============================================================================
# Container Identification & Lifecycle
# ==============================================================================

variable "container_id" {
  type        = number
  description = "Proxmox LXC container ID"
}

variable "container_hostname" {
  type        = string
  description = "Hostname for the LXC container"
  default     = "ct-instance"
}

variable "container_description" {
  type        = string
  description = "Description for the LXC container"
  default     = "LXC container managed by Terraform"
}

variable "unprivileged" {
  type        = bool
  description = "Run container as unprivileged (true) or privileged (false)"
  default     = false
}

# ==============================================================================
# Operating System
# ==============================================================================

variable "template_file_id" {
  type        = string
  description = "Storage volume and filename of the OS template"
}

# ==============================================================================
# Network Configuration
# ==============================================================================

variable "ipv4_address" {
  type        = string
  description = "IPv4 address with CIDR subnet mask (e.g., 192.168.1.50/24)"
}

variable "ipv4_gateway" {
  type        = string
  description = "Default IPv4 gateway"
}

# ==============================================================================
# Compute Resources (CPU & Memory)
# ==============================================================================

variable "cpu_cores" {
  type        = number
  description = "Number of assigned CPU cores"
  default     = 2
}

variable "memory_dedicated" {
  type        = number
  description = "Dedicated RAM in MB"
  default     = 2048
}

variable "memory_swap" {
  type        = number
  description = "Swap space in MB"
  default     = 512
}

# ==============================================================================
# Storage & Mount Points
# ==============================================================================

variable "disk_datastore_id" {
  type        = string
  description = "Target storage pool for the root disk"
  default     = "local"
}

variable "disk_size" {
  type        = number
  description = "Root disk size in GB"
  default     = 20
}

variable "mount_points" {
  type = list(object({
    volume    = string
    path      = string
    read_only = optional(bool, false)
  }))
  description = "List of bind mount points to pass from the host to the container"
  default     = []
}