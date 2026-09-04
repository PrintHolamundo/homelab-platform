# Homelab Platform

Automated pipeline to provision a Debian 13 LXC on Proxmox VE via **Terraform**, configure Docker CE via **Ansible**, and deploy service stacks (Caddy, Portainer, Cloudflared) using a unified **Makefile**. Secrets are securely managed and version-controlled using **Mozilla SOPS** and **Age**.

## Repository Structure

```text
homelab-Platform/
├── .sops.yaml               # SOPS creation rules and Age public key mapping
├── Makefile                 # Orchestration (deploy, destroy, secrets management)
├── terraform-proxmox/       # LXC provisioning & inventory auto-generation
│   └── terraform.enc.json   # Encrypted infrastructure settings (Git tracked)
└── ansible-proxmox/
    ├── vars.enc.yml         # Encrypted secrets and domain settings (Git tracked)
    ├── docker.yml           # Docker CE installation playbook
    ├── services.yml         # Compose stacks deployment playbook
    └── services/            # Caddy, Portainer, Cloudflared configurations
```
*(Note: Plain text files like `terraform.tfvars.json` and `secrets.yml` are ignored by Git and managed dynamically by the Makefile).*

## Prerequisites

Requires Proxmox VE 8.x+, an SSH key pair (`~/.ssh/id_ed25519`), your Age private key, and local tools.

* **Arch:**
  ```bash
  sudo pacman -S terraform ansible openssh make sops age
  ```

* **macOS (Homebrew):**
  ```bash
  brew install hashicorp/tap/terraform ansible make sops age
  ```

## Secrets Management & Configuration

Authentication to Proxmox, Cloudflare tokens, and domains are encrypted in the repository. Before running any operations, expose your Age private key in your environment:

```bash
# If using a key file:
export SOPS_AGE_KEY_FILE=/path/to/your/key.txt

# Or directly as a string:
export SOPS_AGE_KEY="AGE-SECRET-KEY-1..."
```

**To modify infrastructure settings or secrets:**
1. **Decrypt:** Run `make decrypt` to produce local plain-text files.
2. **Edit:** Modify `terraform-proxmox/terraform.tfvars.json` (Proxmox specs, IPs) or `ansible-proxmox/secrets.yml` (domains, tokens).
3. **Encrypt:** Run `make encrypt` to update the `.enc` files and automatically delete the plain-text versions.

## Quickstart

Run the full end-to-end deployment with a single command:

```bash
make deploy
```
*This sequentially runs: `decrypt` (Secrets) -> `infra` (Terraform) -> `ping` (Wait for SSH) -> `provision` (Docker setup) -> `services` (Compose stacks) -> `clean-secrets` (Security wipe).*

### Granular Commands

Execute individual pipeline stages or manage secrets independently:

| Command | Description |
| :--- | :--- |
| `make decrypt` | Decrypts `.enc` files into plain text for local editing. |
| `make encrypt` | Encrypts modified plain text files into `.enc` and wipes plain text. |
| `make clean-secrets` | Manually removes plain text secrets (`secrets.yml`, `*.json`) from disk. |
| `make infra` | Provisions the LXC via Terraform and regenerates `inventory.ini`. |
| `make provision` | Runs the Ansible Docker installation playbook. |
| `make services` | Deploys Caddy, Portainer, and Cloudflared Compose stacks. |
| `make destroy` | Tears down the LXC container and cleans up local secrets. |

## Verification

Check running service stacks inside the container:
```bash
ssh -i ~/.ssh/id_ed25519 root@192.168.100.79 "docker ps"
```

Verify internal reverse proxy routing:
```bash
ssh -i ~/.ssh/id_ed25519 root@192.168.100.79 "curl -I -H 'Host: portainer.yourdomain.com' http://localhost:80"
```