# Image size comparison

Built on the local Apple Silicon host with the root application image and the intentionally
single-stage baseline. `docker image ls` reported:

```text
REPOSITORY:TAG       SIZE
fulfillops:dev       380MB
fulfillops:naive     1.78GB
```

The production image is smaller because it uses the pinned slim Python base, installs the
hashed requirements into a virtual environment in a builder stage, and copies only that
environment plus the application and migration files into the runtime stage. The baseline
uses the full Python image and installs directly into that image. The local Docker size
report is host architecture specific; CI builds the same Dockerfile for linux/amd64.
