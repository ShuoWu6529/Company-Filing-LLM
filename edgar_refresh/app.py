import json
import os
from cik_lookup import SecEdgar
import boto3


def lambda_handler(event, context):
    sec = SecEdgar()
    sec.load_from_sec()
    s3_client = boto3.client("s3")

    response = s3_client.put_object(
        Bucket=os.environ["BUCKET_NAME"],
        Key="company_tickers.json",
        Body=json.dumps(sec.raw_tickers),
    )

    return {
        "statusCode": 200,
        "body": "Successfully updated SEC ticker data!",
    }
