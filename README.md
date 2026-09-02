# Homelab Platform

Automated pipeline to provision a Debian 13 LXC on Proxmox VE via **Terraform**, configure Docker CE via **Ansible**, and deploy service stacks (Caddy, Portainer, Cloudflared) using a unified **Makefile**.

## Repository Structure

```text
homelab-Platform/
├── Makefile                 # Orchestration (deploy, destroy)
├── terraform-proxmox/       # LXC provisioning & inventory auto-generation
│   └── terraform.tfvars     # Infrastructure settings (user created)
└── ansible-proxmox/
    ├── vars.yml             # Secrets and domain settings (user created)
    ├── docker.yml           # Docker CE installation playbook
    ├── services.yml         # Compose stacks deployment playbook
    └── services/            # Caddy, Portainer, Cloudflared configurations
```

## Prerequisites

Requires Proxmox VE 8.x+, an SSH key pair (`~/.ssh/id_ed25519`), and local tools.

* **Arch/CachyOS:** `sudo pacman -S terraform ansible openssh make`
* **macOS (Homebrew):** `brew install hashicorp/tap/terraform ansible make`
* **Debian/Ubuntu:** Install `make`, `ansible` (via pipx), and Terraform.

## Configuration

**1. Infrastructure (Terraform)**
```bash
cp terraform-proxmox/terraform.tfvars.example terraform-proxmox/terraform.tfvars
```
*Edit `terraform.tfvars` with your Proxmox credentials, node target (`pve`), IP allocation (`192.168.100.79/24`), and LXC specs.*

**2. Services & Secrets (Ansible)**
```bash
cp ansible-proxmox/vars.yml.example ansible-proxmox/vars.yml
```
*Edit `vars.yml` with your `base_domain`, `acme_email`, and `cloudflare_tunnel_token`.*

## Quickstart

Run the full end-to-end deployment with a single command:

```bash
make deploy
```
*This sequentially runs: `infra` (Terraform) -> `ping` (Wait for SSH) -> `provision` (Docker setup) -> `services` (Compose stacks).*

### Granular Commands

If you need to execute phases independently or teardown the environment:

| Command | Description |
| :--- | :--- |
| `make infra` | Provisions the LXC via Terraform and regenerates `inventory.ini`. |
| `make provision` | Runs the Ansible Docker installation playbook. |
| `make services` | Deploys Caddy, Portainer, and Cloudflared Compose stacks. |
| `make destroy` | Tears down the LXC container and cleans up Proxmox resources. |

## Verification

Check running service stacks inside the container:
```bash
ssh -i ~/.ssh/id_ed25519 root@192.168.100.79 "docker ps"
```

Verify internal reverse proxy routing:
```bash
ssh -i ~/.ssh/id_ed25519 root@192.168.100.79 "curl -I -H 'Host: portainer.yourdomain.com' http://localhost:80"
```