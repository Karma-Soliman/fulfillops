# FulfillOps

## Local quick start

Create the ignored local environment file and set a local PostgreSQL password:

```sh
cp .env.example .env
```

Start the Compose development stack and check API readiness:

```sh
make up
curl -i http://localhost:8080/health/ready
```

Stop the stack without deleting its database volume:

```sh
make down
```

Compose and kind both use host port 8080; stop one before starting the other. The disposable
checker stack can use a separate host port, for example `LB_HOST_PORT=18080 make test-stack-up`.
