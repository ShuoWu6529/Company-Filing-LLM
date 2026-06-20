import requests


class SecEdgar:
    def __init__(self):
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"user-agent": "MLT CP 28 shuowu1000@gmail.com"}
        r = requests.get(url, headers=headers)
        filejson = r.json()

        self.name_dict = {
            value["title"]: value
            for value in filejson.values()
        }

        self.ticker_dict = {
            value["ticker"]: value
            for value in filejson.values()
        }

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

