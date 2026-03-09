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

LAST_NEWS_POST_FILE = "/tmp/last_news_post.json"
IMAGE_URLS = {
    "market": "https://i.imgur.com/REPLACE_WITH_YOUR_MARKET_CHART.jpg",
    "crypto": "https://i.imgur.com/REPLACE_WITH_BTC_GOLD_CHART.jpg",
    "news": "https://i.imgur.com/REPLACE_WITH_NEWS_CHART.jpg"
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
    prompt = f"""You are a witty stock/crypto commentator with light sarcasm and humor.
Write one short, punchy X post (max 260 chars). Straight to the point, engaging, sarcastic.
Use 2-4 relevant emojis. Never destructive.
Only return the tweet text.
Content: {content}"""
    try:
        res = groq.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0.8, max_tokens=150)
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq error: {e}")
        return None

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
    if not text:
        return False
    media_id = upload_media(IMAGE_URLS.get(image_key))
    try:
        client.create_tweet(text=text, media_ids=[media_id] if media_id else None)
        print(f"✓ Posted: {text[:60]}...")
        return True
    except Exception as e:
        print(f"✗ Post failed: {e}")
        return False

def get_price_data():
    """Fetch SPY, QQQ, VIX, BTC, GLD, SLV with % change"""
    tickers = {"SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "BTC": "BTC-USD", "GLD": "GLD", "SLV": "SLV"}
    lines = []
    for label, ticker in tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="2d")
            if len(df) < 2:
                continue
            price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2]
            change = ((price - prev_price) / prev_price * 100)
            emoji = "📈" if change > 0 else "📉"
            lines.append(f"{label} ${price:,.2f} {emoji} {change:+.2f}%")
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
    return lines

def post_market_snapshot(period_label):
    """Post market open or close snapshot"""
    lines = get_price_data()
    if not lines:
        print(f"No price data for {period_label}")
        return False
    
    content = f"{period_label}\n" + "\n".join(lines)
    tweet = generate_tweet(content)
    return post_tweet(tweet, "market") if tweet else False

def fetch_latest_news():
    """Fetch latest market news"""
    try:
        r = requests.get("https://api.marketaux.com/v1/news/all", params={
            "api_token": MARKEAUX_TOKEN,
            "countries": "us",
            "language": "en",
            "limit": 10,
            "filter_entities": "true"
        }, timeout=10)
        articles = r.json().get("data", [])
        return articles
    except Exception as e:
        print(f"News fetch error: {e}")
        return []

def post_news():
    """Check and post relevant news hourly"""
    articles = fetch_latest_news()
    if not articles:
        return False
    
    last_post_ts = load_json(LAST_NEWS_POST_FILE, {"ts": 0})["ts"]
    relevant = []
    
    for a in articles:
        pub_ts = datetime.fromisoformat(a.get("published_at", "").replace("Z", "+00:00")).timestamp()
        if pub_ts > last_post_ts:
            title_desc = (a.get("title", "") + " " + a.get("description", "")).lower()
            if any(kw in title_desc for kw in MEANINGFUL_KEYWORDS):
                relevant.append(a["title"])
    
    if not relevant:
        return False
    
    # Format news with bullet points
    if len(relevant) == 1:
        content = f"Breaking: {relevant[0]}"
    else:
        content = "Market News:\n" + "\n".join([f"• {title}" for title in relevant[:3]])
    
    tweet = generate_tweet(content)
    if tweet and post_tweet(tweet, "news"):
        save_json(LAST_NEWS_POST_FILE, {"ts": time.time()})
        return True
    return False

def run_bot():
    now = datetime.now(pytz.timezone("US/Eastern"))
    h, m = now.hour, now.minute
    
    # Market open: 9:30 AM
    if h == 9 and 30 <= m <= 35:
        print("📊 Market Open Post")
        post_market_snapshot("🔔 Market Opening (9:30 AM)")
        return
    
    # Market close: 4:00 PM
    if h == 16 and 0 <= m <= 5:
        print("📊 Market Close Post")
        post_market_snapshot("🔚 Market Close (4:00 PM)")
        return
    
    # Check news every 5 mins, post hourly
    if m % 5 == 0:
        print("📰 Checking news...")
        post_news()

# Main loop
print("🤖 Market Bot Started")
while True:
    try:
        run_bot()
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(60)  # Check every minute
