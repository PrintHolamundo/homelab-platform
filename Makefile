.PHONY: deploy infra ping provision services destroy help

.DEFAULT_GOAL := help

deploy: infra ping provision services ## Run full deployment workflow: Terraform -> Wait for SSH -> Ansible -> Services

infra: ## Provision LXC container in Proxmox and generate inventory
	@echo "==> [1/4] Provisioning container with Terraform..."
	cd terraform-proxmox && terraform init && terraform apply -auto-approve

ping: ## Poll until the container SSH service is reachable
	@echo "==> [2/4] Waiting for SSH service to become ready..."
	@cd ansible-proxmox && \
	until ansible docker_nodes -m ping > /dev/null 2>&1; do \
		printf "."; \
		sleep 2; \
	done
	@echo "\nSSH connection established."

provision: ## Install and configure Docker CE and plugins via Ansible
	@echo "==> [3/4] Installing Docker CE via Ansible..."
	cd ansible-proxmox && ansible-playbook docker.yml

services: ## Clone repository and deploy Docker Compose services via Ansible
	@echo "==> [4/4] Deploying Docker Compose services..."
	cd ansible-proxmox && ansible-playbook services.yml

destroy: ## Destroy LXC container and release Proxmox resources
	@echo "==> Destroying container on Proxmox..."
	cd terraform-proxmox && terraform destroy -auto-approve

help: ## Show this help menu
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'