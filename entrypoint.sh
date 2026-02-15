#!/bin/sh
# Dual-mode entrypoint: detects Lambda vs ECS runtime and branches accordingly.
# AWS_LAMBDA_RUNTIME_API is set by the Lambda service, absent on ECS.

if [ -n "$AWS_LAMBDA_RUNTIME_API" ]; then
    # Running on Lambda: start the Runtime Interface Client with our handler
    exec python -m awslambdaric processor.handler.handler
else
    # Running on ECS or locally: execute the default command (CMD)
    exec "$@"
fi
