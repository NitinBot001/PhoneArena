from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup
import requests, re
from urllib.parse import urljoin, quote
import time, os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

app = FastAPI()
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ PhoneDB Scraper ------------------ #
class PhoneDBScraper:
    def __init__(self):
        self.base_url = "https://phonedb.net"
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 503]))
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def search(self, name):
        urls = [
            f"{self.base_url}/index.php?m=device&s=query&q={quote(phone_name)}",
            f"{self.base_url}/search?q={quote(phone_name)}",
            f"{self.base_url}/index.php?m=device&s=list&q={quote(phone_name)}"
        ]

        for url in urls:
            try:
                res = self.session.get(url, timeout=10)
                soup = BeautifulSoup(res.content, 'html.parser')
                for a in soup.find_all('a', href=True):
                    if 'device' in a['href']:
                        return urljoin(self.base_url, a['href'])
            except: continue
        return None

    def get_specs(self, url):
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.content, 'html.parser')
            title = soup.find('h1') or soup.find('title')
            name = title.get_text(strip=True) if title else "Unknown"
            specs = {}
            for row in soup.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = re.sub(r'[^\w\s]', '', cells[0].text.strip())
                    val = re.sub(r'\s+', ' ', cells[1].text.strip())
                    if key and val:
                        specs[key] = val
            images = [urljoin(self.base_url, img['src']) for img in soup.find_all('img', src=True) if 'device' in img['src']]
            return {"name": name, "images": images[:3], "specs": specs, "source": url, "provider": "PhoneDB"}
        except:
            return None

    def scrape(self, name):
        url = self.search(name)
        return self.get_specs(url) if url else None

# ------------------ GSMArena Scraper ------------------ #
class GSMArenaScraper:
    def __init__(self):
        self.base_url = "https://www.gsmarena.com"
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})

    def search(self, name):
        try:
            res = self.session.get(f"{self.base_url}/results.php3", params={'sQuickSearch': 'yes', 'sName': name}, timeout=10)
            soup = BeautifulSoup(res.content, 'html.parser')
            for a in soup.select('.makers a'):
                if name.lower().replace(" ", "") in a.get_text(strip=True).lower().replace(" ", ""):
                    return urljoin(self.base_url, a['href'])
        except: return None

    def get_specs(self, url):
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.content, 'html.parser')
            name = (soup.find('h1') or soup.find('title')).get_text(strip=True)
            specs = {}
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) == 2:
                    key = re.sub(r'[^\w\s]', '', cells[0].text.strip())
                    val = re.sub(r'\s+', ' ', cells[1].text.strip())
                    specs[key] = val
            images = [urljoin(url, img['src']) for img in soup.find_all('img', src=True) if 'phones' in img['src']]
            return {"name": name, "images": images[:3], "specs": specs, "source": url, "provider": "GSMArena"}
        except:
            return None

    def scrape(self, name):
        url = self.search(name)
        return self.get_specs(url) if url else None

# ------------------ HTML View Route ------------------ #
@app.get("/", response_class=HTMLResponse)
def form_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/", response_class=HTMLResponse)
def scrape_ui(request: Request, phone_name: str = Form(...)):
    data = PhoneDBScraper().scrape(phone_name)
    if not data:
        data = GSMArenaScraper().scrape(phone_name)
    return templates.TemplateResponse("index.html", {"request": request, "data": data, "query": phone_name})