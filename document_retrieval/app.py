import json
import logging
import os
import time
import boto3
from botocore.exceptions import ClientError
from cik_lookup import SecEdgar
from errors import (
    SecLambdaError,
    ValidationError,
    StorageError,
    BedrockThrottleError,
    BedrockInvocationError,
    BedrockParseError,
    DownstreamInvocationError,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUIRED_FIELDS = ("question", "ticker", "year", "period")


def _validate_input(event):
    missing = [field for field in REQUIRED_FIELDS if not event.get(field)]
    if missing:
        raise ValidationError(
            f"Missing required field(s): {', '.join(missing)}", missing_fields=missing
        )
    return event["question"], event["ticker"], event["year"], event["period"]


def _invoke_edgar_refresh(request_id):
    function_name = os.environ["EDGAR_REFRESH_FUNCTION_NAME"]
    lambda_client = boto3.client("lambda")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({}).encode("utf-8"),
    )

    if response.get("FunctionError"):
        payload = json.loads(response["Payload"].read())
        logger.error(
            "EdgarRefreshFunction invocation failed [requestId=%s] [%s]: %s",
            request_id,
            response["FunctionError"],
            payload,
        )
        raise DownstreamInvocationError(
            "Downstream EdgarRefreshFunction invocation failed",
            function_name=function_name,
            function_error=response["FunctionError"],
        )


def _load_ticker_data(request_id):
    sec = SecEdgar()
    try:
        sec.load_from_bucket()
        return sec
    except StorageError as exc:
        if exc.context.get("aws_error_code") != "NoSuchKey":
            raise

    logger.info(
        "Ticker data missing in S3 [requestId=%s], invoking EdgarRefreshFunction to backfill",
        request_id,
    )
    _invoke_edgar_refresh(request_id)
    sec.load_from_bucket()
    return sec


def _fetch_document(sec, ticker, year, period):
    try:
        cik, _, _ = sec.ticker_to_cik(ticker)
    except KeyError as exc:
        raise ValidationError(f"Unknown ticker: {ticker}", ticker=ticker) from exc

    if period in ("FY", "Q4"):
        return sec.annual_filing(cik, year)

    try:
        quarter = int(period.lstrip("Q"))
    except ValueError as exc:
        raise ValidationError(f"Invalid period: {period}", period=period) from exc

    return sec.quarterly_filing(cik, year, quarter)


def _invoke_bedrock(message, request_id):
    model_arn = os.environ["BEDROCK_MODEL_ARN"]
    bedrock = boto3.client("bedrock-runtime")
    start = time.monotonic()
    try:
        response = bedrock.invoke_model(
            modelId=model_arn,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": message}],
                }
            ),
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        logger.error(
            "Bedrock invoke_model failed [requestId=%s] [%s]: %s",
            request_id,
            error_code,
            exc,
        )
        if error_code == "ThrottlingException":
            raise BedrockThrottleError(
                "Bedrock throttled the request, retry after backoff",
                model=model_arn,
            ) from exc
        raise BedrockInvocationError(
            "Bedrock model invocation failed",
            model=model_arn,
            aws_error_code=error_code,
        ) from exc

    latency_ms = round((time.monotonic() - start) * 1000)

    try:
        response_body = json.loads(response["body"].read())
        answer = response_body["content"][0]["text"]
        usage = response_body["usage"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.error(
            "Bedrock response parse failed [requestId=%s]: %s", request_id, exc
        )
        raise BedrockParseError("Unexpected Bedrock response shape") from exc

    return {
        "answer": answer,
        "meta": {
            "model": model_arn,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "latency_ms": latency_ms,
        },
    }


def lambda_handler(event, context):
    request_id = context.aws_request_id

    try:
        question, ticker, year, period = _validate_input(event)

        logger.info(
            "DocumentRetrievalFunction start [requestId=%s] ticker=%s year=%s period=%s",
            request_id,
            ticker,
            year,
            period,
        )

        sec = _load_ticker_data(request_id)
        document = _fetch_document(sec, ticker, year, period)
        message = document + question
        result = _invoke_bedrock(message, request_id)

        return {"statusCode": 200, "body": json.dumps(result)}

    except SecLambdaError as exc:
        logger.error(
            "DocumentRetrievalFunction failed [requestId=%s] [%s] %s | context=%s",
            request_id,
            exc.error_code,
            exc.message,
            exc.context,
        )
        return error_response(exc, request_id)

    except Exception as exc:
        logger.error(
            "DocumentRetrievalFunction unhandled error [requestId=%s]: %s",
            request_id,
            exc,
            exc_info=True,
        )
        return error_response(SecLambdaError("Internal error"), request_id)
