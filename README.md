# Company-LLM-Lambda

Serverless application, deployed with AWS SAM, that keeps a local mirror of SEC EDGAR ticker data and answers questions about a company's 10-K/10-Q filings using Amazon Bedrock.

- `edgar_refresh` - `EdgarRefreshFunction`. Runs on a daily schedule, pulls `company_tickers.json` from SEC EDGAR, and writes it to the `EdgarBucket` S3 bucket.
- `document_retrieval` - `DocumentRetrievalFunction`. Given a `ticker`/`year`/`period`/`question`, looks up the CIK, fetches the matching filing from SEC EDGAR, and asks a Bedrock model to answer the question against it. If the ticker cache is missing from S3, it invokes `EdgarRefreshFunction` synchronously to backfill it first.
- `lookup_package` - `CikLookupModule` Lambda layer shared by both functions. Contains `cik_lookup.py` (the `SecEdgar` client for SEC EDGAR + S3) and `errors.py` (the structured error types both functions raise).
- `events` - Sample invocation events.
- `template.yaml` - The SAM template defining all of the above plus the `EdgarBucket` S3 bucket.

Both functions return a structured JSON body (`{"error": ..., "message": ..., "requestId": ...}` on failure) so callers never see a raw traceback, and every code path logs the invocation's `requestId` for tracing in CloudWatch.

## Prerequisites

* SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* [Python 3.12](https://www.python.org/downloads/)
* Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community) (needed for `sam build` and `sam local invoke`)

## Build and deploy

```bash
sam build
sam deploy --guided
```

`sam deploy --guided` walks through stack name, region, and confirmation prompts and saves your choices to `samconfig.toml`; after the first run you can just use `sam deploy`.

## Invoke locally

`sam build` installs each component's dependencies from its own `requirements.txt` (`edgar_refresh/`, `document_retrieval/`, `lookup_package/`) and stages the deployment package under `.aws-sam/build`.

```bash
sam local invoke EdgarRefreshFunction --event events/event.json
sam local invoke DocumentRetrievalFunction --event events/event.json
```

## Invoke the deployed functions

```bash
sam remote invoke EdgarRefreshFunction --stack-name Company-LLM-Lambda -e '{}'

sam remote invoke DocumentRetrievalFunction --stack-name Company-LLM-Lambda \
  -e '{"question": "What are the main risk factors?", "ticker": "AAPL", "year": 2023, "period": "FY"}'
```

## Fetch, tail, and filter Lambda function logs

```bash
sam logs -n DocumentRetrievalFunction --stack-name Company-LLM-Lambda --tail
```

Every log line is prefixed with the invocation's request ID, so you can isolate a single execution with `grep <requestId>`. See the [SAM CLI logging docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html) for more filtering options.

## Cleanup

```bash
sam delete --stack-name Company-LLM-Lambda
```

## Resources

See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to the SAM specification, the SAM CLI, and serverless application concepts.
