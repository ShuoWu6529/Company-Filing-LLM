import json


class SecLambdaError(Exception):
    """Base class for errors that map to a structured Lambda error response."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message, **context):
        super().__init__(message)
        self.message = message
        self.context = context


class ValidationError(SecLambdaError):
    status_code = 400
    error_code = "validation_error"


class EdgarNetworkError(SecLambdaError):
    status_code = 502
    error_code = "edgar_unreachable"


class EdgarAccessDeniedError(SecLambdaError):
    status_code = 502
    error_code = "edgar_access_denied"


class EdgarNotFoundError(SecLambdaError):
    status_code = 404
    error_code = "edgar_not_found"


class BedrockThrottleError(SecLambdaError):
    status_code = 429
    error_code = "bedrock_throttled"


class BedrockInvocationError(SecLambdaError):
    status_code = 502
    error_code = "bedrock_invocation_failed"


class BedrockParseError(SecLambdaError):
    status_code = 500
    error_code = "bedrock_parse_error"


class StorageError(SecLambdaError):
    status_code = 500
    error_code = "storage_error"


class DownstreamInvocationError(SecLambdaError):
    status_code = 502
    error_code = "downstream_invocation_failed"


def error_response(err, request_id):
    body = {"error": err.error_code, "message": err.message, "requestId": request_id}
    if err.context:
        body["details"] = err.context
    return {"statusCode": err.status_code, "body": json.dumps(body)}
