import json


def lambda_handler(event, context):
    return {
        "statusCode": 501,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "FastAPI agent runtime has not been deployed yet.",
                "detail": "This placeholder keeps the Cognito-protected API surface provisioned by Terraform."
            }
        ),
    }
