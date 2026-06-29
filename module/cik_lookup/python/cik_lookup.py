import requests

SEC_HEADERS = {"User-Agent": "MLT CP28 shuowu1000@gmail.com"}

class SecEdgar:
    def __init__(self):
        self.headers = SEC_HEADERS
        self.name_dict = {}
        self.ticker_dict = {}
        self.raw_tickers = None

    def load_from_sec(self):
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=self.headers)
        self.raw_tickers = r.json()
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
    
    def _fetch_company_filings(self, cik):
        cik = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        r = requests.get(url, headers=self.headers)
        filejson = r.json()
        filings = filejson["filings"]["recent"]
        return filings
    
    def _fetch_company_document(self, cik, accession_number, primary_document):
        accession_number = accession_number.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{primary_document}"
        r = requests.get(url, headers=self.headers)
        filetext = r.text
        return filetext

    def _fetch_company_facts(self, cik):
        cik = str(cik).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        r = requests.get(url, headers=self.headers)
        filejson = r.json()
        return filejson["facts"]
    
    def _fetch_financial_reports(self, cik, year):
        filings = self._fetch_company_filings(cik)
        company_facts = self._fetch_company_facts(cik)
        shares = company_facts["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]

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
        reports  = self._fetch_financial_reports(cik, year)
        accession_number, primary_document = reports[3]        
        ten_k = self._fetch_company_document(cik, accession_number, primary_document)
        return ten_k

    def quarterly_filing(self, cik, year, quarter):
        reports  = self._fetch_financial_reports(cik, year)
        accession_number, primary_document = reports[quarter - 1]        
        ten_q = self._fetch_company_document(cik, accession_number, primary_document)
        return ten_q