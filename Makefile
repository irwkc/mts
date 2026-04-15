.PHONY: up down logs
up:
	bash scripts/local-up.sh

down:
	docker compose down 2>/dev/null || docker-compose down

logs:
	docker compose logs -f --tail=100 2>/dev/null || docker-compose logs -f --tail=100
