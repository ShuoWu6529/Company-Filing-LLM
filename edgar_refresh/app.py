import json
import logging
import os
import boto3
from botocore.exceptions import ClientError
from cik_lookup import SecEdgar
from errors import SecLambdaError, StorageError, error_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_id = context.aws_request_id
    logger.info("EdgarRefreshFunction start [requestId=%s]", request_id)

    try:
        sec = SecEdgar()
        sec.load_from_sec()

        s3_client = boto3.client("s3")
        try:
            s3_client.put_object(
                Bucket=os.environ["BUCKET_NAME"],
                Key="company_tickers.json",
                Body=json.dumps(sec.raw_tickers),
            )
        except ClientError as exc:
            raise StorageError(
                "Failed to write ticker data to S3",
                bucket=os.environ.get("BUCKET_NAME"),
                aws_error_code=exc.response.get("Error", {}).get("Code"),
            ) from exc

        logger.info("EdgarRefreshFunction succeeded [requestId=%s]", request_id)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Successfully updated SEC ticker data!"}),
        }

    except SecLambdaError as exc:
        logger.error(
            "EdgarRefreshFunction failed [requestId=%s] [%s] %s | context=%s",
            request_id,
            exc.error_code,
            exc.message,
            exc.context,
        )
        return error_response(exc, request_id)

    except Exception as exc:
        logger.error(
            "EdgarRefreshFunction unhandled error [requestId=%s]: %s",
            request_id,
            exc,
            exc_info=True,
        )
        return error_response(SecLambdaError("Internal error"), request_id)
