import os
import time
import json
import yfinance as yf
from datetime import datetime
import pytz
import requests
from groq import Groq
import tweepy

MARKEAUX_TOKEN = os.getenv("MARKEAUX_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

LAST_NEWS_FILE = "/tmp/last_news.json"
LAST_POST_FILE = "/tmp/last_post.json"
IMAGE_URLS = {
    "market": "https://i.imgur.com/REPLACE_WITH_YOUR_MARKET_CHART.jpg",
    "crypto": "https://i.imgur.com/REPLACE_WITH_BTC_GOLD_CHART.jpg",
    "quiet": "https://i.imgur.com/REPLACE_WITH_QUIET_CHART.jpg"
}
MEANINGFUL_KEYWORDS = ["fed","fomc","powell","rate cut","rate hike","jobs","nfp","unemployment","cpi","inflation","ppi","gdp","earnings","beat estimates","missed estimates","merger","acquisition","deal","geopolitical","tariff","china","ukraine","announcement","breaking"]

def load_json(file, default):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

auth = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
api_v1 = tweepy.API(auth)
client = tweepy.Client(consumer_key=X_API_KEY, consumer_secret=X_API_SECRET, access_token=X_ACCESS_TOKEN, access_token_secret=X_ACCESS_SECRET)
groq = Groq(api_key=GROQ_API_KEY)

def generate_tweet(content):
    prompt = f"""You are a witty stock/crypto commentator with light sarcasm.
Write one short, punchy X post (max 260 chars). Straight to the point, engaging.
Use 2-4 relevant emojis. Never destructive.
Only return the tweet text.
Content: {content}"""
    try:
        res = groq.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=150)
        return res.choices[0].message.content.strip()
    except:
        return "Market moving... stay tuned"

def upload_media(url):
    try:
        r = requests.get(url, stream=True, timeout=10)
        temp = "/tmp/temp.jpg"
        with open(temp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        media = api_v1.media_upload(temp)
        os.remove(temp)
        return media.media_id_string
    except:
        return None

def post_tweet(text, image_key="market"):
    media_id = upload_media(IMAGE_URLS.get(image_key))
    try:
        client.create_tweet(text=text, media_ids=[media_id] if media_id else None)
        print("Posted:", text[:80])
        save_json(LAST_POST_FILE, {"timestamp": time.time()})
        return True
    except Exception as e:
        print("Post failed:", e)
        return False

def run_bot():
    now = datetime.now(pytz.timezone("US/Eastern"))
    h, m = now.hour, now.minute
    
    tickers = ["SPY", "QQQ", "^VIX", "BTC-USD", "GC=F", "SI=F", "^TNX"]
    lines = []
    for t in tickers:
        try:
            df = yf.Ticker(t).history(period="2d")
            if len(df) < 1:
                continue
            price = df['Close'].iloc[-1]
            change = ((price - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100) if len(df) > 1 else 0
            emoji = "up" if change > 0 else "down"
            label = t.replace("^", "").replace("-USD", "").replace("=F", "")
            lines.append(f"{label} ${price:,.2f} {emoji} {change:+.2f}%")
        except:
            pass
    
    price_block = "\n".join(lines) or "Prices loading..."
    
    if h == 9 and 25 <= m <= 40:
        post_tweet(generate_tweet(f"9:30 AM Opening\n{price_block}"), "market")
        return
    elif h == 13 and m <= 15:
        post_tweet(generate_tweet(f"Midday Check\n{price_block}"), "market")
        return
    elif 16 <= h <= 17 and m <= 30:
        post_tweet(generate_tweet(f"End of Day Close\n{price_block}"), "market")
        return
    
    last_news = load_json(LAST_NEWS_FILE, {"ts": "2026-01-01T00:00:00Z"})["ts"]
    try:
        r = requests.get("https://api.marketaux.com/v1/news/all", params={"api_token": MARKEAUX_TOKEN, "countries": "us", "language": "en", "limit": 4, "published_after": last_news, "filter_entities": "true"})
        articles = r.json().get("data", [])
        if articles:
            save_json(LAST_NEWS_FILE, {"ts": articles[0]["published_at"]})
    except:
        articles = []
    
    relevant = [a for a in articles if any(kw in (a.get("title","") + " " + a.get("description","")).lower() for kw in MEANINGFUL_KEYWORDS)]
    if relevant:
        content = "Fresh news:\n" + "\n".join([a["title"] for a in relevant[:2]])
        img_key = "crypto" if "btc" in content.lower() else "market"
        post_tweet(generate_tweet(content), img_key)
        return
    
    last_post = load_json(LAST_POST_FILE, {"timestamp": 0})["timestamp"]
    if time.time() - last_post > 7200:
        post_tweet(generate_tweet(f"Quiet markets for now...\n{price_block}\nEyes open"), "quiet")

# Demo post on startup
print("Posting demo...")
tickers = ["SPY", "QQQ"]
lines = []
for t in tickers:
    try:
        df = yf.Ticker(t).history(period="2d")
        if len(df) < 1:
            continue
        price = df['Close'].iloc[-1]
        change = ((price - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100) if len(df) > 1 else 0
        emoji = "📈" if change > 0 else "📉"
        lines.append(f"{t} ${price:,.2f} {emoji} {change:+.2f}%")
    except:
        pass

demo_content = "Market snapshot:\n" + "\n".join(lines)
post_tweet(generate_tweet(demo_content), "market")
print("Demo posted!")

# Normal loop
while True:
    run_bot()
    time.sleep(3600)
