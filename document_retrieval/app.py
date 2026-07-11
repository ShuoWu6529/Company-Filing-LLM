import json
import time
import os
import boto3
from cik_lookup import SecEdgar

RESPONSE_MODEL = "us.anthropic.claude-sonnet-4-5-20250514-v1:0"


def lambda_handler(event, context):
    sec = SecEdgar()
    sec.load_from_bucket()
    question = event["question"]
    ticker = event["ticker"]
    year = event["year"]
    period = event["period"]
    cik, _, _ = sec.ticker_to_cik(ticker)

    if period == "FY" or period == "Q4":
        document = sec.annual_filing(cik, year)
    else:
        quarter = int(period.lstrip("Q"))
        document = sec.quarterly_filing(cik, year, quarter)

    message = document + question
    bedrock = boto3.client("bedrock-runtime")

    start = time.monotonic()
    response = bedrock.invoke_model(
        modelId=os.environ["BEDROCK_MODEL_ARN"],
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": message}
                ],
            }
        ),
    )
    latency_ms = round((time.monotonic() - start) * 1000)

    response_body = json.loads(response["body"].read())

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "answer": response_body["content"][0]["text"],
                "meta": {
                    "model": RESPONSE_MODEL,
                    "input_tokens": response_body["usage"]["input_tokens"],
                    "output_tokens": response_body["usage"]["output_tokens"],
                    "latency_ms": latency_ms,
                },
            }
        ),
    }
