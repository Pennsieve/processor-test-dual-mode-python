"""
Lambda handler that bridges the invocation payload to environment variables,
then runs the same processing logic as ECS mode.
"""

import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
log = logging.getLogger("processor-test")


def handler(event, context):
    """
    Lambda entry point. Exports per-invocation payload fields as env vars
    so the processor logic works identically to ECS mode.

    Static env vars (PENNSIEVE_API_HOST, PENNSIEVE_API_HOST2, ENVIRONMENT, REGION,
    DEPLOYMENT_MODE) are already set on the Lambda function configuration.
    """
    log.info("Lambda handler invoked with event: %s", event)

    # Bridge per-invocation payload → env vars
    os.environ["INPUT_DIR"] = event.get("inputDir", "")
    os.environ["OUTPUT_DIR"] = event.get("outputDir", "")
    os.environ["INTEGRATION_ID"] = event.get("integrationId", "")
    os.environ["SESSION_TOKEN"] = event.get("sessionToken", "")
    os.environ["REFRESH_TOKEN"] = event.get("refreshToken", "")

    # Bridge any additional keys (e.g. injected secrets) to env vars.
    # Keys that are already handled above or are non-string are skipped.
    _known_keys = {"inputDir", "outputDir", "integrationId", "sessionToken",
                   "refreshToken", "computeNodeId", "executionRunId",
                   "llmGovernorFunction"}
    for key, value in event.items():
        if key not in _known_keys and isinstance(value, str):
            os.environ[key] = value

    # Run the same logic as ECS mode
    from processor.main import run
    run()

    return {"status": "success", "integrationId": event.get("integrationId", "")}
