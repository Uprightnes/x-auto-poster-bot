import tweepy
import feedparser
import requests
from bs4 import BeautifulSoup
import time
import random
import os
from datetime import datetime, timezone, timedelta
import json
import re

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')

SCHEDULE_FILE = 'scheduled_posts.json'
POSTED_URLS_FILE = 'posted_urls.json'
DAILY_TRACKER_FILE = 'daily_post_count.json'

# 🛑 SAFETY LIMIT (Total max posts per day)
DAILY_LIMIT = 10 

# 🕐 FRESHNESS LIMIT — drop unposted items older than this many hours
# This is what actually guarantees "latest update only" — not the calendar date.
MAX_QUEUE_AGE_HOURS = 36

# ⏰ POSTING SCHEDULE (UTC TIMES)
# Nigeria is UTC+1. So 7 UTC = 8 AM Nigeria.
# These 10 slots spread the 10 posts throughout the day.
ALLOWED_HOURS_UTC = [
    7,   # 8 AM WAT (Morning Rush)
    8,   # 9 AM WAT
    10,  # 11 AM WAT
    12,  # 1 PM WAT (Lunch)
    14,  # 3 PM WAT
    16,  # 5 PM WAT (Closing)
    17,  # 6 PM WAT
    19,  # 8 PM WAT (Evening Scroll)
    20,  # 9 PM WAT
    21   # 10 PM WAT (Late Night)
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {} if filename == DAILY_TRACKER_FILE else []
    return {} if filename == DAILY_TRACKER_FILE else []

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def save_posted_url(url):
    posted = load_json(POSTED_URLS_FILE)
    if isinstance(posted, list):
        if url not in posted:
            posted.append(url)
            # Keep only last 500 URLs to prevent file from getting too large
            if len(posted) > 500:
                posted = posted[-500:]
            save_json(POSTED_URLS_FILE, posted)
    else:
        save_json(POSTED_URLS_FILE, [url])

def authenticate_twitter():
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        print("✓ Successfully authenticated with X API")
        return client
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return None

# ============================================================================
# DAILY CLEANUP & DATA MANAGEMENT
# ============================================================================

def cleanup_old_data():
    """Clean up old data when it's a new day.

    IMPORTANT: Freshness of queued posts is judged by `added_at` (when the
    item was actually scraped), NOT by whether `scheduled_time` happens to
    fall on today's calendar date. The old logic deleted perfectly fresh,
    still-unposted items just because UTC midnight had passed since they
    were queued. Now a post only gets dropped once it's actually stale
    (older than MAX_QUEUE_AGE_HOURS), regardless of which day it is.
    """
    tracker = load_json(DAILY_TRACKER_FILE)
    
    # Get Nigeria time (UTC+1)
    nigeria_tz = timezone(timedelta(hours=1))
    today_str = datetime.now(nigeria_tz).strftime('%Y-%m-%d')
    
    is_new_day = (not tracker or tracker.get('date') != today_str)

    if is_new_day:
        print(f"🆕 NEW DAY DETECTED: {today_str}")
        print("🧹 Cleaning up old data...")
        
        # 1. Reset daily tracker
        tracker = {'date': today_str, 'count': 0}
        save_json(DAILY_TRACKER_FILE, tracker)

    # 2. Prune the schedule by FRESHNESS, every run (not just on day change).
    #    - Already-posted items are dropped (no longer needed).
    #    - Unposted items older than MAX_QUEUE_AGE_HOURS are dropped (stale).
    #    - Everything else survives, even across a day boundary.
    schedule = load_json(SCHEDULE_FILE)
    if isinstance(schedule, list):
        now_utc = datetime.now(timezone.utc)
        cleaned_schedule = []
        dropped_stale = 0
        dropped_posted = 0

        for post in schedule:
            if post.get('posted', False):
                dropped_posted += 1
                continue

            added_at_str = post.get('added_at')
            if added_at_str:
                try:
                    added_at = datetime.fromisoformat(added_at_str.replace('Z', '+00:00'))
                    age_hours = (now_utc - added_at).total_seconds() / 3600
                    if age_hours > MAX_QUEUE_AGE_HOURS:
                        dropped_stale += 1
                        continue
                except Exception:
                    # If we can't parse it, don't silently keep junk forever —
                    # but don't nuke it on a parse hiccup either. Keep it once;
                    # it'll get judged again next run.
                    pass

            cleaned_schedule.append(post)

        if len(cleaned_schedule) != len(schedule):
            save_json(SCHEDULE_FILE, cleaned_schedule)
            print(f"  ✓ Scheduled posts: {len(schedule)} → {len(cleaned_schedule)} "
                  f"(dropped {dropped_posted} posted, {dropped_stale} stale >{MAX_QUEUE_AGE_HOURS}h)")

    # 3. Trim posted URLs list (keep last 500) — only needs to happen once a day
    if is_new_day:
        posted_urls = load_json(POSTED_URLS_FILE)
        if isinstance(posted_urls, list) and len(posted_urls) > 500:
            posted_urls = posted_urls[-500:]
            save_json(POSTED_URLS_FILE, posted_urls)
            print(f"  ✓ Posted URLs trimmed to {len(posted_urls)}")
        
        print("✅ New day cleanup completed!")
    
    return tracker

# ============================================================================
# CHECKERS: TIME & LIMITS
# ============================================================================

def is_posting_hour():
    """Checks if the current hour is in our allowed schedule"""
    current_hour_utc = datetime.now(timezone.utc).hour
    
    if current_hour_utc in ALLOWED_HOURS_UTC:
        print(f"✅ Current UTC Hour ({current_hour_utc}) is in allowed schedule.")
        return True
    else:
        print(f"⏳ Current UTC Hour ({current_hour_utc}) is NOT in allowed schedule.")
        print(f"   Allowed UTC hours: {ALLOWED_HOURS_UTC}")
        print("   Script will run maintenance (scraping) but will NOT post.")
        return False

def check_daily_limit():
    """Returns True if we are allowed to post, False if limit reached"""
    tracker = load_json(DAILY_TRACKER_FILE)
    
    # Get Nigeria time (UTC+1)
    nigeria_tz = timezone(timedelta(hours=1))
    today_str = datetime.now(nigeria_tz).strftime('%Y-%m-%d')
    
    # Reset if new day
    if not tracker or tracker.get('date') != today_str:
        print(f"🔄 New day detected ({today_str}). Resetting counter to 0.")
        tracker = {'date': today_str, 'count': 0}
        save_json(DAILY_TRACKER_FILE, tracker)
        return True
    
    current_count = tracker.get('count', 0)
    print(f"📊 Daily Stats: {current_count}/{DAILY_LIMIT} posted today.")
    
    if current_count >= DAILY_LIMIT:
        print("🛑 Daily limit reached! Skipping post.")
        return False
        
    return True

def increment_daily_count():
    """Increment the daily post count"""
    tracker = load_json(DAILY_TRACKER_FILE)
    
    # Get Nigeria time (UTC+1)
    nigeria_tz = timezone(timedelta(hours=1))
    today_str = datetime.now(nigeria_tz).strftime('%Y-%m-%d')
    
    # Reset if it's a new day
    if not tracker or tracker.get('date') != today_str:
        tracker = {'date': today_str, 'count': 1}
    else:
        tracker['count'] = tracker.get('count', 0) + 1
    
    save_json(DAILY_TRACKER_FILE, tracker)
    print(f"📈 Incremented daily count to {tracker['count']}")

# ============================================================================
# SMART DATA EXTRACTION (PRESERVED)
# ============================================================================

def extract_smart_details(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    details = {'salary': None, 'email': None, 'benefits': []}
    
    # Salary
    salary_patterns = [r'(\$|₦|N)\s?[\d,kK]+(\s*(-|—|to)\s*(\$|₦|N)\s?[\d,kK]+)?\s*(/yr|/mo|/year|/month|annually)?']
    for pattern in salary_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            s = match.group(0).strip().replace('—', '-')
            if len(s) > 3: details['salary'] = s; break
    
    # Email
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    ignore = ['noreply', 'support', 'help', 'info', 'example', 'wixpress']
    for email in emails:
        if not any(x in email.lower() for x in ignore):
            details['email'] = email; break
    
    # Benefits
    benefit_keywords = {
        'Health': ['health insurance', 'medical', 'dental'],
        'Remote': ['remote', 'work from home', 'wfh'],
        'Visa': ['visa sponsorship', 'relocation'],
        'Equity': ['stock options', 'equity', 'shares'],
        'Flexible': ['flexible hours', 'async'],
        'Vacation': ['unlimited pto', 'paid time off', 'vacation'],
        'Crypto': ['crypto', 'bitcoin', 'web3']
    }
    found_benefits = []
    text_lower = text.lower()
    for label, patterns in benefit_keywords.items():
        if any(p in text_lower for p in patterns):
            found_benefits.append(label)
            if len(found_benefits) >= 3: break
    
    details['benefits'] = found_benefits
    return details

# ============================================================================
# RSS FEED SCRAPERS
# ============================================================================

def fetch_rss_jobs(feed_url, source_name, is_remote=False, country="Nigeria"):
    jobs = []
    print(f"📡 Fetching: {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(feed_url, headers=headers, timeout=15)
        feed = feedparser.parse(response.content)
        
        if not feed.entries: return jobs
        
        posted_urls = load_json(POSTED_URLS_FILE)
        if not isinstance(posted_urls, list): posted_urls = []
        
        for entry in feed.entries[:5]: # Top 5 per feed
            try:
                raw_html = ""
                if hasattr(entry, 'content'): raw_html = entry.content[0].value
                elif hasattr(entry, 'summary'): raw_html = entry.summary
                elif hasattr(entry, 'description'): raw_html = entry.description
                
                job_url = entry.link.split('?')[0] if '?' in entry.link else entry.link
                if job_url in posted_urls: continue
                
                details = extract_smart_details(raw_html)
                
                title_lower = entry.title.lower()
                if 'lagos' in title_lower: location = 'Lagos 🇳🇬'
                elif 'abuja' in title_lower: location = 'Abuja 🇳🇬'
                elif is_remote: location = 'Remote 🌍'
                else: location = f'{country} 🇳🇬'
                
                jobs.append({
                    'title': entry.title.strip(),
                    'url': job_url,
                    'location': location,
                    'salary': details['salary'],
                    'email': details['email'],
                    'benefits': details['benefits'],
                    'type': 'job'
                })
            except: continue
    except Exception as e:
        print(f"  ✗ Error: {e}")
    return jobs

def scrape_scholarships():
    scholarships = []
    print("🎓 Fetching Scholarships...")
    rss_feeds = ["https://www.opportunitiesforafricans.com/feed/", "https://www.scholars4dev.com/feed/"]
    posted_urls = load_json(POSTED_URLS_FILE)
    if not isinstance(posted_urls, list): posted_urls = []
    
    for feed_url in rss_feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                try:
                    job_url = entry.link.split('?')[0] if '?' in entry.link else entry.link
                    if job_url in posted_urls: continue
                    
                    title = entry.title.strip()
                    if not any(w in title.lower() for w in ['scholarship', 'grant', 'funded']): continue
                    
                    year = datetime.now().year
                    if str(year) not in title and str(year + 1) not in title: title = f"{title} {year + 1}"
                    is_funded = 'fully funded' in title.lower()
                    
                    scholarships.append({
                        'title': title,
                        'url': job_url,
                        'location': 'International 🌍',
                        'salary': 'Fully Funded' if is_funded else 'Scholarship',
                        'email': None,
                        'benefits': ['Tuition', 'Stipend'] if is_funded else ['Education'],
                        'type': 'scholarship'
                    })
                except: continue
        except: continue
    return scholarships

# ============================================================================
# QUEUE MANAGEMENT
# ============================================================================

def format_rich_tweet(item):
    icon = '🎓' if item['type'] == 'scholarship' else '🔥'
    title = item['title'][:70] + "..." if len(item['title']) > 70 else item['title']
    tweet = f"{icon} {title}\n\n📍 {item['location']}"
    if item['salary']: tweet += f" | 💰 {item['salary']}"
    if item['benefits']: tweet += "\n" + " | ".join([f"✅ {b}" for b in item['benefits'][:3]])
    tweet += "\n\n👉 APPLY:"
    if item['email']: tweet += f"\n📧 {item['email']}"
    tweet += f"\n🔗 {item['url']}"
    
    tags = []
    if item['type'] == 'scholarship': tags = ['#Scholarships', '#StudyAbroad', '#FullyFunded']
    elif 'Remote' in item['location']: tags = ['#RemoteJobs', '#TechJobs', '#Wfh']
    else: tags = ['#NigeriaJobs', '#Lagos', '#JobSearch']
    
    tweet += f"\n\n{' '.join(tags)}"
    return tweet

def refill_queue(schedule):
    """Scrape new opportunities and add them to queue.

    Posts are spread across the REMAINING allowed hours today (and overflow
    to tomorrow's hours if there are more posts than remaining slots), so a
    refill doesn't bunch everything into a single timestamp.
    """
    print("\n🔍 Refilling Queue...")
    all_opportunities = []
    all_opportunities.extend(fetch_rss_jobs("https://remoteok.com/remote-jobs.rss", "RemoteOK", is_remote=True))
    all_opportunities.extend(fetch_rss_jobs("https://hotnigerianjobs.com/feed/", "HotNigerianJobs", is_remote=False))
    all_opportunities.extend(fetch_rss_jobs("https://www.myjobmag.com/feed", "MyJobMag", is_remote=False))
    all_opportunities.extend(scrape_scholarships())
    
    random.shuffle(all_opportunities)

    current_utc = datetime.now(timezone.utc)
    current_hour = current_utc.hour

    # Hours still ahead of us today
    remaining_today = [h for h in ALLOWED_HOURS_UTC if h > current_hour]

    # Already-used slots (today or future) so we don't double-book a slot
    # that an earlier, still-unposted item already occupies.
    used_slots = set()
    for p in schedule:
        if not p.get('posted', False) and p.get('scheduled_time'):
            try:
                used_slots.add(p['scheduled_time'])
            except Exception:
                pass

    formatted_posts = []
    day_offset = 0
    hour_pool = list(remaining_today) if remaining_today else []

    for opp in all_opportunities[:10]:  # Limit to 10 new posts per refill
        scheduled_time = None
        # Walk forward through hour_pool / next days until we find a free slot
        while True:
            if not hour_pool:
                day_offset += 1
                hour_pool = list(ALLOWED_HOURS_UTC)

            hour = hour_pool.pop(0)
            candidate_date = current_utc + timedelta(days=day_offset)
            candidate = candidate_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            candidate_iso = candidate.isoformat()

            if candidate_iso not in used_slots:
                scheduled_time = candidate
                used_slots.add(candidate_iso)
                break
            # else: slot taken, loop again and pull the next hour

        formatted_posts.append({
            'tweet_text': format_rich_tweet(opp),
            'url': opp['url'],
            'posted': False,
            'scheduled_time': scheduled_time.isoformat(),
            'added_at': current_utc.isoformat()
        })
    
    return formatted_posts

# ============================================================================
# MAIN LOGIC
# ============================================================================

def main():
    print(f"\n{'='*60}")
    print(f"🤖 Smart Scheduler Bot")
    print(f"⏰ UTC: {datetime.now(timezone.utc).strftime('%H:%M:%S')}")
    
    # Get Nigeria time
    nigeria_tz = timezone(timedelta(hours=1))
    nigeria_time = datetime.now(nigeria_tz).strftime('%Y-%m-%d %H:%M:%S')
    print(f"🇳🇬 Nigeria: {nigeria_time}")
    print(f"{'='*60}\n")
    
    # 0. FIRST: Clean up stale/posted data (freshness-based, not date-based)
    tracker = cleanup_old_data()
    
    # 1. MAINTENANCE: Always refill queue if low
    schedule = load_json(SCHEDULE_FILE)
    if not isinstance(schedule, list): 
        schedule = []
    
    print(f"📊 Daily Stats: {tracker.get('count', 0)}/{DAILY_LIMIT} posts today")
    print(f"📋 Queue: {len(schedule)} scheduled posts")
    
    if len(schedule) < 5:  # Refill if queue is getting low
        print("📭 Queue is low! Scraping new opportunities...")
        new_posts = refill_queue(schedule)
        if new_posts:
            schedule.extend(new_posts)
            save_json(SCHEDULE_FILE, schedule)
            print(f"✅ Added {len(new_posts)} new posts to queue.")
    
    # 2. CHECK: Is it time to post?
    if not is_posting_hour():
        print("⏳ Not a posting hour. Maintenance complete.")
        return
    
    # 3. CHECK: Daily limit
    if not check_daily_limit():
        return
    
    # 4. ACTION: Post Tweet
    if schedule:
        # Authenticate only when we actually need to post
        client = authenticate_twitter()
        if not client: 
            return
    
        # Find the next unposted item
        post_to_publish = None
        post_index = None
        
        for i, post in enumerate(schedule):
            if not post.get('posted', False):
                post_to_publish = post
                post_index = i
                break
        
        if post_to_publish:
            try:
                print(f"\n📤 Posting: {post_to_publish['tweet_text'][:50]}...")
                print(f"📅 Today's date: {datetime.now(nigeria_tz).strftime('%Y-%m-%d %H:%M:%S')}")
                
                response = client.create_tweet(text=post_to_publish['tweet_text'])
                save_posted_url(post_to_publish['url'])
                increment_daily_count()
                
                # Mark as posted with timestamp
                schedule[post_index]['posted'] = True
                schedule[post_index]['posted_at'] = datetime.now(timezone.utc).isoformat()
                save_json(SCHEDULE_FILE, schedule)
                
                # Verify increment worked
                updated_tracker = load_json(DAILY_TRACKER_FILE)
                print(f"📊 New daily count: {updated_tracker.get('count', 0)}/{DAILY_LIMIT}")
                print(f"📎 URL: {post_to_publish['url']}")
                print("✅ Tweet sent successfully!")
                
            except Exception as e:
                print(f"❌ Error posting: {e}")
                # Don't mark as posted if there was an error
        else:
            print("📭 No unposted items in queue.")
            # Clean up all posted items to make room for new ones
            unposted_posts = [p for p in schedule if not p.get('posted', False)]
            save_json(SCHEDULE_FILE, unposted_posts)
            print(f"🧹 Cleaned queue: {len(schedule)} → {len(unposted_posts)} posts")

if __name__ == "__main__":
    main()
