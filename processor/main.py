"""
Test processor for dual-mode (ECS + Lambda) compute node validation.

Reads files from INPUT_DIR, creates uniquely-named symlinks in OUTPUT_DIR,
tests internet connectivity, and logs all results. Designed for testing
DAG workflows including diamond-shaped merge scenarios.
"""

import os
import sys
import socket
import logging
import uuid
import time

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("processor-test")

# Unique ID for this processor run to avoid symlink name collisions in merges
PROCESSOR_RUN_ID = uuid.uuid4().hex[:8]


def get_config():
    """Read configuration from environment variables."""
    input_dir = os.environ.get("INPUT_DIR", "")
    output_dir = os.environ.get("OUTPUT_DIR", "")
    integration_id = os.environ.get("INTEGRATION_ID", "unknown")
    session_token = os.environ.get("SESSION_TOKEN", "")
    api_host = os.environ.get("PENNSIEVE_API_HOST", "")
    api_host2 = os.environ.get("PENNSIEVE_API_HOST2", "")
    environment = os.environ.get("ENVIRONMENT", "unknown")
    region = os.environ.get("REGION", "unknown")
    deployment_mode = os.environ.get("DEPLOYMENT_MODE", "")

    return {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "integration_id": integration_id,
        "session_token": session_token,
        "api_host": api_host,
        "api_host2": api_host2,
        "environment": environment,
        "region": region,
        "deployment_mode": deployment_mode,
    }


def test_env_vars(config):
    """Log all environment variables the platform should provide."""
    log.info("=== TEST: Environment Variables ===")
    results = []
    for key, value in config.items():
        present = bool(value)
        status = "PASS" if present else "WARN"
        display = value if key != "session_token" else ("***" if value else "(empty)")
        log.info("  %s: %s = %s", status, key, display)
        results.append((key, present))
    return results


def test_directories(config):
    """Verify INPUT_DIR exists and OUTPUT_DIR is writable."""
    log.info("=== TEST: Directory Access ===")
    input_dir = config["input_dir"]
    output_dir = config["output_dir"]

    input_exists = os.path.isdir(input_dir)
    log.info("  INPUT_DIR exists: %s (%s)", input_exists, input_dir)

    output_exists = os.path.isdir(output_dir)
    if not output_exists:
        try:
            os.makedirs(output_dir, exist_ok=True)
            log.info("  OUTPUT_DIR created: %s", output_dir)
            output_exists = True
        except OSError as e:
            log.error("  OUTPUT_DIR create failed: %s", e)

    output_writable = False
    if output_exists:
        test_file = os.path.join(output_dir, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            output_writable = True
            log.info("  OUTPUT_DIR writable: True")
        except OSError as e:
            log.error("  OUTPUT_DIR writable: False (%s)", e)

    return input_exists, output_writable


def test_internet_access(config):
    """Test internet connectivity and validate against deployment mode.

    Deployment modes:
      - basic:     internet expected (public subnets, direct access)
      - secure:    internet expected (private subnets with NAT gateway)
      - compliant: NO internet expected (private subnets, no NAT)
      - (empty):   no validation (local/unknown mode)
    """
    log.info("=== TEST: Internet Access ===")
    deployment_mode = config["deployment_mode"]
    is_lambda = bool(os.environ.get("AWS_LAMBDA_RUNTIME_API"))
    # Lambda in VPC has no internet in basic mode (no public IP, no NAT)
    if is_lambda and deployment_mode == "basic":
        expect_internet = False
    else:
        expect_internet = deployment_mode != "compliant"
    log.info("  Deployment mode: %s", deployment_mode or "(not set)")
    log.info("  Runtime: %s", "Lambda" if is_lambda else "ECS/Local")
    if deployment_mode:
        log.info("  Internet expected: %s", expect_internet)

    # DNS resolution
    dns_ok = False
    try:
        addr = socket.getaddrinfo("api.pennsieve.net", 443, socket.AF_INET)
        dns_ok = True
        log.info("  DNS resolution: PASS (api.pennsieve.net -> %s)", addr[0][4][0])
    except socket.gaierror as e:
        log.info("  DNS resolution: FAIL (%s)", e)

    # HTTP request
    http_ok = False
    try:
        resp = requests.get("https://api.pennsieve.net/health", timeout=5)
        http_ok = resp.status_code < 500
        log.info("  HTTP request: PASS (status %d)", resp.status_code)
    except requests.RequestException as e:
        log.info("  HTTP request: FAIL (%s)", e)

    internet_available = dns_ok and http_ok
    log.info("  Internet available: %s", internet_available)

    # Validate against deployment mode
    valid = True
    if deployment_mode:
        if expect_internet and not internet_available:
            log.error("  VALIDATION FAILED: %s mode expects internet but connectivity test failed", deployment_mode)
            valid = False
        elif not expect_internet and internet_available:
            log.error("  VALIDATION FAILED: %s mode should NOT have internet but connectivity test passed", deployment_mode)
            valid = False
        else:
            log.info("  VALIDATION PASSED: internet access matches %s mode expectation", deployment_mode)

    return dns_ok, http_ok, valid


def test_symlink_creation(config):
    """
    Create uniquely-named symlinks in OUTPUT_DIR for each file in INPUT_DIR.

    Each symlink is named: {run_id}_{original_filename}
    This avoids collisions when multiple processors feed into a merge node
    in a diamond DAG.
    """
    log.info("=== TEST: Symlink Creation ===")
    input_dir = config["input_dir"]
    output_dir = config["output_dir"]
    created = []

    if not os.path.isdir(input_dir):
        log.error("  INPUT_DIR does not exist, skipping symlinks")
        return created

    files = []
    for entry in os.listdir(input_dir):
        full_path = os.path.join(input_dir, entry)
        if os.path.isfile(full_path) or os.path.islink(full_path):
            files.append((entry, full_path))

    if not files:
        log.warning("  No files found in INPUT_DIR")
        return created

    log.info("  Found %d file(s) in INPUT_DIR", len(files))

    for filename, source_path in files:
        # Unique name: {run_id}_{original} to avoid merge collisions
        link_name = f"{PROCESSOR_RUN_ID}_{filename}"
        link_path = os.path.join(output_dir, link_name)
        try:
            # Resolve to absolute path for symlink target
            abs_source = os.path.realpath(source_path)
            os.symlink(abs_source, link_path)
            log.info("  Created: %s -> %s", link_name, abs_source)
            created.append(link_name)
        except OSError as e:
            log.error("  Failed to create symlink %s: %s", link_name, e)

    return created


def run():
    """Run all tests and report summary."""
    start = time.time()
    log.info("=" * 60)
    log.info("Processor Test - Dual Mode Validation")
    log.info("Run ID: %s", PROCESSOR_RUN_ID)
    log.info("Runtime: %s", "Lambda" if os.environ.get("AWS_LAMBDA_RUNTIME_API") else "ECS/Local")
    log.info("PID: %d", os.getpid())
    log.info("=" * 60)

    config = get_config()
    log.info("Integration ID: %s", config["integration_id"])

    # Run tests
    env_results = test_env_vars(config)
    input_ok, output_ok = test_directories(config)
    dns_ok, http_ok, internet_valid = test_internet_access(config)
    symlinks = test_symlink_creation(config)

    # Summary
    elapsed = time.time() - start
    log.info("=" * 60)
    log.info("=== SUMMARY ===")
    log.info("  Deployment mode: %s", config["deployment_mode"] or "(not set)")
    log.info("  Environment vars present: %d/%d", sum(1 for _, v in env_results if v), len(env_results))
    log.info("  INPUT_DIR accessible: %s", input_ok)
    log.info("  OUTPUT_DIR writable: %s", output_ok)
    log.info("  DNS resolution: %s", dns_ok)
    log.info("  HTTP connectivity: %s", http_ok)
    log.info("  Internet validation: %s", "PASS" if internet_valid else "FAIL")
    log.info("  Symlinks created: %d", len(symlinks))
    log.info("  Elapsed: %.2fs", elapsed)
    log.info("=" * 60)

    if not input_ok or not output_ok:
        log.error("CRITICAL: directory access failed")
        sys.exit(1)

    if not internet_valid:
        log.error("CRITICAL: internet access does not match deployment mode '%s'", config["deployment_mode"])
        sys.exit(1)

    log.info("All tests completed successfully")


if __name__ == "__main__":
    run()
