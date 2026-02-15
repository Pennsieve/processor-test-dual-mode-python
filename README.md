# processor-test-dual-mode-python

Test processor for validating Pennsieve compute node infrastructure. Runs as both an ECS Fargate task and an AWS Lambda function from the same container image.

## What it does

On every invocation, this processor runs four validation tests:

1. **Environment variables** - Verifies all platform-provided env vars are present (`INPUT_DIR`, `OUTPUT_DIR`, `PENNSIEVE_API_HOST`, `DEPLOYMENT_MODE`, etc.)
2. **Directory access** - Confirms `INPUT_DIR` exists and `OUTPUT_DIR` is writable
3. **Internet connectivity** - Tests DNS resolution and HTTP access to `api.pennsieve.net`, then validates the result against `DEPLOYMENT_MODE` (basic/secure expect internet, compliant expects none)
4. **Symlink creation** - Creates a uniquely-named symlink in `OUTPUT_DIR` for each file in `INPUT_DIR`, using the format `{run_id}_{filename}` to avoid collisions

The processor exits 0 on success and non-zero if any critical test fails (directory access or internet validation mismatch).

## Dual-mode architecture

The image includes the AWS Lambda Runtime Interface Client (`awslambdaric`). A runtime-detecting `entrypoint.sh` checks `AWS_LAMBDA_RUNTIME_API`:

- **ECS / local**: runs `python -m processor.main` (reads env vars directly)
- **Lambda**: starts the RIC, which invokes `processor.handler.handler` (bridges payload fields to env vars, then calls the same logic)

## Testing DAG merges

Each processor run generates a unique 8-character run ID. Output symlinks are prefixed with this ID (`{run_id}_{filename}`), so multiple instances of this processor can feed into a downstream merge node without name collisions. This makes it suitable for testing diamond-shaped DAGs:

```
     [A]
    /   \
  [B]   [C]    ← both create symlinks with unique prefixes
    \   /
     [D]       ← receives merged output from B and C
```

## Local development

Build and run with docker-compose:

```sh
make build    # build the Docker image
make run      # run via docker-compose (ECS mode)
make clean    # remove output files
```

Environment variables for local runs are in `dev.env`.

## Project structure

```
processor/
  main.py           # Core logic: tests + symlink creation
  handler.py        # Lambda handler (payload → env vars bridge)
  requirements.txt  # awslambdaric, requests
entrypoint.sh       # Runtime detection (Lambda vs ECS)
Dockerfile          # Dual-mode image with RIC
docker-compose.yml  # Local testing
dev.env             # Local environment variables
data/
  input/            # Sample input files for local testing
  output/           # Output directory (gitignored)
```

## Environment variables

| Variable | Source (ECS) | Source (Lambda) | Description |
|----------|-------------|-----------------|-------------|
| `INPUT_DIR` | Container override | Payload → handler | Path to input files on EFS |
| `OUTPUT_DIR` | Container override | Payload → handler | Path to write output on EFS |
| `INTEGRATION_ID` | Container override | Payload → handler | Workflow run identifier |
| `SESSION_TOKEN` | Container override | Payload → handler | API session token |
| `PENNSIEVE_API_HOST` | Container override | Function config | Pennsieve API base URL |
| `PENNSIEVE_API_HOST2` | Container override | Function config | Pennsieve API v2 base URL |
| `ENVIRONMENT` | Container override | Function config | Environment name |
| `REGION` | Container override | Function config | AWS region |
| `DEPLOYMENT_MODE` | Container override | Function config | `basic`, `secure`, or `compliant` |
