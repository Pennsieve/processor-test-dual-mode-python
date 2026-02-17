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

    # Run the same logic as ECS mode
    from processor.main import run
    run()

    return {"status": "success", "integrationId": event.get("integrationId", "")}
