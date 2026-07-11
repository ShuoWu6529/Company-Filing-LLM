import json
import os
import warnings

import boto3
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from botocore.exceptions import ClientError

from errors import EdgarAccessDeniedError, EdgarNetworkError, EdgarNotFoundError, StorageError

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

SEC_HEADERS = {"User-Agent": "MLT CP28 shuowu1000@gmail.com"}
REQUEST_TIMEOUT_SECONDS = 10


class SecEdgar:
    def __init__(self):
        self.headers = SEC_HEADERS
        self.name_dict = {}
        self.ticker_dict = {}
        self.raw_tickers = None

    def _get(self, url):
        try:
            r = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            raise EdgarNetworkError(
                f"Request to SEC EDGAR failed: {exc}", url=url
            ) from exc

        if r.status_code == 403:
            raise EdgarAccessDeniedError(
                "SEC EDGAR denied access (check User-Agent header)",
                url=url,
                upstream_status_code=403,
            )
        if r.status_code == 404:
            raise EdgarNotFoundError(
                "SEC EDGAR resource not found", url=url, upstream_status_code=404
            )
        if r.status_code != 200:
            raise EdgarNetworkError(
                f"SEC EDGAR returned unexpected status {r.status_code}",
                url=url,
                upstream_status_code=r.status_code,
            )

        return r

    def load_from_sec(self):
        r = self._get("https://www.sec.gov/files/company_tickers.json")
        self.raw_tickers = r.json()
        self._build_dicts(self.raw_tickers)

    def load_from_bucket(self):
        s3 = boto3.client("s3")
        try:
            response = s3.get_object(
                Bucket=os.environ["BUCKET_NAME"], Key="company_tickers.json"
            )
        except ClientError as exc:
            raise StorageError(
                "Failed to read ticker data from S3",
                bucket=os.environ.get("BUCKET_NAME"),
                aws_error_code=exc.response.get("Error", {}).get("Code"),
            ) from exc
        self.raw_tickers = json.loads(response["Body"].read())
        self._build_dicts(self.raw_tickers)

    def _build_dicts(self, filejson):
        self.name_dict = {value["title"]: value for value in filejson.values()}
        self.ticker_dict = {value["ticker"]: value for value in filejson.values()}

    def name_to_cik(self, name):
        company_info = self.name_dict[name]
        cik = company_info["cik_str"]
        ticker = company_info["ticker"]
        return cik, name, ticker

    def ticker_to_cik(self, ticker):
        company_info = self.ticker_dict[ticker]
        cik = company_info["cik_str"]
        name = company_info["title"]
        return cik, name, ticker

    def _padded_cik(self, cik):
        return str(cik).zfill(10)

    def _fetch_company_filings(self, cik):
        url = f"https://data.sec.gov/submissions/CIK{self._padded_cik(cik)}.json"
        r = self._get(url)
        filejson = r.json()
        filings = filejson["filings"]["recent"]
        return filings

    def _fetch_company_document(self, cik, accession_number, primary_document):
        accession_number = accession_number.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{primary_document}"
        r = self._get(url)
        filetext = r.text
        return filetext

    def _fetch_company_facts(self, cik):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self._padded_cik(cik)}.json"
        r = self._get(url)
        filejson = r.json()
        return filejson["facts"]

    def _fetch_financial_reports(self, cik, year):
        filings = self._fetch_company_filings(cik)
        company_facts = self._fetch_company_facts(cik)
        shares = company_facts["dei"]["EntityCommonStockSharesOutstanding"]["units"][
            "shares"
        ]

        fy_accession_numbers = set()
        financial_reports_names = {"10-K", "10-Q"}
        for share in shares:
            fy = share.get("fy", -1)
            form = share.get("form", "")

            if fy == year and form in financial_reports_names:
                fy_accession_numbers.add(share["accn"])

        accession_numbers = filings["accessionNumber"]
        primary_documents = filings["primaryDocument"]
        filing_metadata = zip(accession_numbers, primary_documents)

        reports = []
        for accession_number, primary_document in filing_metadata:
            if accession_number not in fy_accession_numbers:
                continue
            reports.append((accession_number, primary_document))

        reports.reverse()
        return reports

    def annual_filing(self, cik, year):
        reports = self._fetch_financial_reports(cik, year)
        accession_number, primary_document = reports[3]
        ten_k = self._fetch_company_document(cik, accession_number, primary_document)
        return self._parse_for_content(ten_k)

    def quarterly_filing(self, cik, year, quarter):
        reports = self._fetch_financial_reports(cik, year)
        accession_number, primary_document = reports[quarter - 1]
        ten_q = self._fetch_company_document(cik, accession_number, primary_document)
        return self._parse_for_content(ten_q)

    def _parse_for_content(self, text):
        soup = BeautifulSoup(text, "lxml")

        for hidden in soup.select('[style*="display:none"]'):
            hidden.decompose()

        return soup.get_text()
