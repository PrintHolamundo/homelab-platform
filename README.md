# Homelab Platform

Automated infrastructure pipeline to provision a Debian 13 LXC on Proxmox VE via Terraform, configure Docker CE via Ansible, and deploy containerized services (Caddy, Cloudflared, Homepage, Media stack, Paperless, Immich, Odoo, Home Assistant) using a unified Makefile. Secrets are encrypted using Mozilla SOPS and Age.

## Prerequisites

- Proxmox VE 8.x+
- SSH key pair (`~/.ssh/id_ed25519`)
- Installed tools: `terraform`, `ansible`, `make`, `sops`, `age`

## Quickstart

1. Export your Age private key:
```bash
export SOPS_AGE_KEY="AGE-SECRET-KEY-1..."
# or: export SOPS_AGE_KEY_FILE=/path/to/key.txt
```

2. Deploy the full stack:
```bash
make deploy
```
*Executes: decrypt secrets -> provision LXC (Terraform) -> wait for SSH -> install Docker (Ansible) -> deploy services -> wipe plain text secrets.*

## Common Commands

- `make deploy`: Run full provisioning and deployment pipeline.
- `make services`: Deploy or update Docker Compose service stacks.
- `make decrypt`: Decrypt `.enc` files into plain text for editing.
- `make encrypt`: Encrypt modified plain text files and wipe local plain text.
- `make destroy`: Destroy the LXC container on Proxmox.