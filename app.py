import re
import threading
from collections import Counter
from urllib.parse import quote_plus

from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

REGISTRATION = "FA23-BDS-007"
NEWS_SOURCE = "Islamabad Post"
BASE_URL = "https://islamabadpost.com.pk"

app = Flask(__name__)
lock = threading.Lock()  # one Chrome at a time, the server has little RAM

STOPWORDS = set("""a an the and or but if of to in on for with at by from is are was
were be been it its this that these those as he she they we you i his her their our
not no has have had will would can could said says also than then which who whom
about after before over into more most such""".split())


def make_driver():
    opts = webdriver.ChromeOptions()
    opts.binary_location = "/usr/bin/chromium"
    opts.page_load_strategy = "eager"
    for a in ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-gpu", "--window-size=1280,1024"]:
        opts.add_argument(a)
    d = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=opts)
    d.set_page_load_timeout(40)
    return d


def first_result_url(driver, keyword):
    driver.get(f"{BASE_URL}/?s={quote_plus(keyword)}")
    selectors = ["h3.entry-title a", ".td_module_wrap h3 a", "article h2 a",
                 "h2.entry-title a", ".entry-title a", "article h3 a"]
    for sel in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            href = el.get_attribute("href")
            if href and href.startswith(BASE_URL):
                return href
    return None


def article_text(driver, url):
    driver.get(url)
    for sel in [".td-post-content p", ".entry-content p", "article p"]:
        paras = [p.text.strip() for p in driver.find_elements(By.CSS_SELECTOR, sel)]
        paras = [p for p in paras if len(p) > 40]
        if paras:
            return " ".join(paras)
    return ""


def summarize(text, n=3):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 30]
    if len(sentences) <= n:
        return " ".join(sentences)
    words = [w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOPWORDS]
    freq = Counter(words)
    scored = []
    for i, s in enumerate(sentences):
        toks = [w for w in re.findall(r"[a-z']+", s.lower()) if w not in STOPWORDS]
        score = sum(freq[w] for w in toks) / (len(toks) + 1)
        scored.append((score, i))
    top = sorted(i for _, i in sorted(scored, reverse=True)[:n])
    return " ".join(sentences[i] for i in top)


@app.route("/")
def home():
    return f"News API by {REGISTRATION} - source: {NEWS_SOURCE}. Use /get?keyword=your_word"


@app.route("/get")
def get():
    keyword = request.args.get("keyword", "").strip()
    out = {"registration": REGISTRATION, "newssource": NEWS_SOURCE,
           "keyword": keyword, "url": "", "summary": ""}
    if not keyword:
        out["summary"] = "Please provide ?keyword=..."
        return jsonify(out), 400
    with lock:
        driver = None
        try:
            driver = make_driver()
            url = first_result_url(driver, keyword)
            if not url:
                out["summary"] = "No search results found."
                return jsonify(out)
            out["url"] = url
            text = article_text(driver, url)
            out["summary"] = summarize(text) if text else "Could not extract article text."
        except Exception as e:
            out["summary"] = f"Error: {type(e).__name__}"
        finally:
            if driver:
                driver.quit()
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
