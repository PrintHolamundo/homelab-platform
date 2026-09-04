.PHONY: deploy infra ping provision services destroy help encrypt decrypt clean-secrets

.DEFAULT_GOAL := help

TF_DIR     := terraform-proxmox
ANS_DIR    := ansible-proxmox
TF_PLAIN   := $(TF_DIR)/terraform.tfvars.json
TF_ENC     := $(TF_DIR)/terraform.enc.json
ANS_PLAIN  := $(ANS_DIR)/secrets.yml
ANS_ENC    := $(ANS_DIR)/secrets.enc.yml

##@ Main Workflow
deploy: decrypt infra ping provision services clean-secrets ## Run full deployment workflow: decrypt, provision, and clean plain secrets

destroy: decrypt ## Destroy LXC container on Proxmox and clean local secrets
	@echo "==> Destroying container on Proxmox..."
	cd $(TF_DIR) && terraform destroy -auto-approve
	@$(MAKE) clean-secrets

##@ Provisioning Steps
infra: ## Provision LXC container with Terraform
	@echo "==> [1/4] Provisioning container with Terraform..."
	cd $(TF_DIR) && terraform init && terraform apply -auto-approve

ping: ## Wait until the container SSH service is ready
	@echo "==> [2/4] Waiting for SSH service to become ready..."
	@cd $(ANS_DIR) && \
	until ansible docker_nodes -m ping > /dev/null 2>&1; do \
		printf "."; \
		sleep 2; \
	done
	@echo "\nSSH connection established."

provision: ## Install Docker CE via Ansible
	@echo "==> [3/4] Installing Docker CE via Ansible..."
	cd $(ANS_DIR) && ansible-playbook docker.yml

services: ## Deploy Docker Compose services via Ansible
	@echo "==> [4/4] Deploying Docker Compose services..."
	cd $(ANS_DIR) && ansible-playbook services.yml

##@ Secrets Management (SOPS)
encrypt: ## Encrypt plain text secrets into .enc files and wipe plain text
	@echo "🔒 Encrypting secrets..."
	sops --encrypt $(TF_PLAIN) > $(TF_ENC)
	sops --encrypt $(ANS_PLAIN) > $(ANS_ENC)
	@$(MAKE) clean-secrets

decrypt: ## Decrypt .enc files to plain text for local execution or editing
	@echo "🔓 Decrypting secrets..."
	sops --decrypt $(TF_ENC) > $(TF_PLAIN)
	sops --decrypt $(ANS_ENC) > $(ANS_PLAIN)

clean-secrets: ## Remove temporary plain text secrets
	@echo "🧹 Cleaning up plain text secrets..."
	@rm -f $(TF_PLAIN) $(ANS_PLAIN)

##@ Help
help: ## Show this help menu
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'