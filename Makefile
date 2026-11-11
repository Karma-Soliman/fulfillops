.PHONY: up down ps logs test-stack-up test-stack-down

# Start the development stack and build its stub image.
up:
	docker compose up -d --build

# Stop the development stack while keeping the named database volume.
down:
	docker compose down

# Show the development service states.
ps:
	docker compose ps

# Follow development service logs.
logs:
	docker compose logs -f

# Start the isolated destructive-checker stack on localhost:8080.
test-stack-up:
	docker compose -f compose.yaml -f compose.test.yaml -p fulfillops-test up -d --build

# Destroy only disposable test containers and their database volume.
test-stack-down:
	docker compose -f compose.yaml -f compose.test.yaml -p fulfillops-test down -v
