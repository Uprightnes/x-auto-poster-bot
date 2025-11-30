
import tweepy
import feedparser
import time
import random
import os
from datetime import datetime, timedelta
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
LAST_RUN_FILE = 'last_scrape_date.txt'
POSTED_URLS_FILE = 'posted_urls.json'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_schedule():
    """Load scheduled posts from file"""
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return []

def save_schedule(posts):
    """Save scheduled posts to file"""
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(posts, f, indent=2)

def load_posted_urls():
    """Load URLs that have been posted already"""
    if os.path.exists(POSTED_URLS_FILE):
        with open(POSTED_URLS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_posted_url(url):
    """Save a URL as posted"""
    posted = load_posted_urls()
    if url not in posted:
        posted.append(url)
        # Keep only last 500 URLs
        posted = posted[-500:]
        with open(POSTED_URLS_FILE, 'w') as f:
            json.dump(posted, f, indent=2)

def get_last_scrape_date():
    """Get the last date we scraped for jobs"""
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, 'r') as f:
            return f.read().strip()
    return None

def set_last_scrape_date(date):
    """Set the last scrape date"""
    with open(LAST_RUN_FILE, 'w') as f:
        f.write(date)

def authenticate_twitter():
    """Authenticate with X/Twitter API"""
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
# RSS FEED SCRAPING (100% RELIABLE!)
# ============================================================================

def get_jobs_via_rss():
    """Get real Nigerian + international jobs via public RSS feeds"""
    
    rss_feeds = [
        # Nigerian Jobs
        "https://www.jobberman.com/jobs/rss",
        "https://www.myjobmag.com/rss/nigeria",
        "https://ng.indeed.com/rss?q=&l=Nigeria",
        "https://hotnigerianjobs.com/feed/",
        
        # International Remote Jobs
        "https://remoteok.com/remote-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-time-jobs.rss",
        "https://rss.indeed.com/rss?q=remote",
        
        # Scholarships
        "https://www.scholarshipportal.com/rss/scholarships.xml",
        "https://www.opportunitiesforafricans.com/feed/",
        "https://www.scholars4dev.com/feed/",
    ]
    
    all_opportunities = []
    posted_urls = load_posted_urls()
    
    print("\n📡 Fetching opportunities from RSS feeds...")
    
    for feed_url in rss_feeds:
        try:
            print(f"  → Checking: {feed_url.split('/')[2]}...")
            feed = feedparser.parse(feed_url)
            
            if not feed.entries:
                print(f"    ⚠️ No entries found")
                continue
            
            count = 0
            for entry in feed.entries[:15]:  # Limit per feed
                try:
                    title = entry.title.strip()
                    link = entry.link.strip()
                    
                    # Skip if already posted
                    if link in posted_urls:
                        continue
                    
                    # Skip duplicates in current batch
                    if any(j.get('url') == link for j in all_opportunities):
                        continue
                    
                    # Determine if it's a scholarship or job
                    is_scholarship = any(word in title.lower() for word in ['scholarship', 'grant', 'study abroad', 'funded'])
                    
                    # Extract some basic info from title
                    location = extract_location_from_title(title)
                    work_type = extract_work_type_from_title(title)
                    
                    all_opportunities.append({
                        'title': title,
                        'url': link,
                        'type': 'scholarship' if is_scholarship else 'job',
                        'location': location,
                        'work_type': work_type,
                        'source': feed_url.split('/')[2]
                    })
                    count += 1
                    
                except Exception as e:
                    continue
            
            print(f"    ✓ Found {count} new opportunities")
            time.sleep(1)  # Be respectful
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
            continue
    
    random.shuffle(all_opportunities)
    print(f"\n✅ Total: {len(all_opportunities)} fresh opportunities from RSS feeds!")
    
    return all_opportunities[:15]  # Return top 15

def extract_location_from_title(title):
    """Try to extract location from job title"""
    title_lower = title.lower()
    
    # Nigerian states
    nigerian_states = ['lagos', 'abuja', 'port harcourt', 'kano', 'ibadan', 'kaduna', 'enugu']
    for state in nigerian_states:
        if state in title_lower:
            return state.title()
    
    # Common keywords
    if 'remote' in title_lower or 'worldwide' in title_lower:
        return 'Remote/Worldwide'
    if 'nigeria' in title_lower:
        return 'Nigeria'
    
    return 'See Job Post'

def extract_work_type_from_title(title):
    """Try to extract work type from title"""
    title_lower = title.lower()
    
    if 'remote' in title_lower:
        return 'Remote'
    if 'hybrid' in title_lower:
        return 'Hybrid'
    if 'onsite' in title_lower or 'on-site' in title_lower:
        return 'Onsite'
    
    return 'See Details'

# ============================================================================
# FORMATTING FUNCTIONS
# ============================================================================

def format_job_tweet(job):
    """Format job as tweet text"""
    
    # Basic format
    tweet = f"🔥 {job['title']}\n\n"
    
    # Add location if available
    if job.get('location') and job['location'] != 'See Job Post':
        tweet += f"📍 Location: {job['location']}\n"
    
    # Add work type if available  
    if job.get('work_type') and job['work_type'] != 'See Details':
        tweet += f"💼 Type: {job['work_type']}\n"
    
    tweet += f"\n👉 APPLY HERE: {job['url']}"
    
    # Truncate if too long
    if len(tweet) > 280:
        max_title_length = 280 - len(job['url']) - 50
        short_title = job['title'][:max_title_length] + "..."
        tweet = f"🔥 {short_title}\n\n"
        if job.get('location'):
            tweet += f"📍 {job['location']}\n"
        tweet += f"\n👉 APPLY: {job['url']}"
    
    return tweet

def format_scholarship_tweet(scholarship):
    """Format scholarship as tweet text"""
    
    year = datetime.now().year
    title = scholarship['title']
    
    # Add year if not present
    if str(year) not in title and str(year + 1) not in title:
        title = f"{title} {year + 1}"
    
    tweet = f"🎓 {title}\n\n"
    
    # Check if it mentions funding
    if any(word in title.lower() for word in ['fully funded', 'full scholarship', 'funded']):
        tweet += "💰 Fully Funded\n"
    
    # Add location if available
    if scholarship.get('location') and scholarship['location'] != 'See Job Post':
        tweet += f"🌍 {scholarship['location']}\n"
    
    tweet += f"\n👉 APPLY HERE: {scholarship['url']}"
    
    # Truncate if too long
    if len(tweet) > 280:
        max_title_length = 280 - len(scholarship['url']) - 50
        short_title = title[:max_title_length] + "..."
        tweet = f"🎓 {short_title}\n\n"
        tweet += f"👉 APPLY: {scholarship['url']}"
    
    return tweet

# ============================================================================
# SCHEDULING FUNCTIONS
# ============================================================================

def generate_posting_times(count=15):
    """Generate posting times throughout the day (Nigeria WAT = UTC+1)"""
    now = datetime.utcnow()
    times = []
    
    # Posting times in UTC (these will be 1 hour later in Nigeria WAT)
    # 6am UTC = 7am WAT, 8am UTC = 9am WAT, etc.
    hours = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    
    for i in range(min(count, len(hours))):
        post_time = now.replace(hour=hours[i % len(hours)], minute=0, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for next occurrence
        if post_time < now:
            post_time += timedelta(days=1)
        
        times.append(post_time.isoformat() + 'Z')
    
    # If we need more times, add some for tomorrow
    while len(times) < count:
        base_time = datetime.utcnow() + timedelta(days=1)
        for hour in hours:
            if len(times) >= count:
                break
            post_time = base_time.replace(hour=hour, minute=0, second=0, microsecond=0)
            times.append(post_time.isoformat() + 'Z')
    
    return times[:count]

def should_scrape_today():
    """Check if we should scrape for new jobs today"""
    last_scrape = get_last_scrape_date()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Scrape if we haven't scraped today OR if it's around 4-6am UTC (5-7am WAT)
    current_hour = datetime.utcnow().hour
    
    if last_scrape != today and current_hour >= 4:
        return True
    
    return False

def scrape_and_schedule():
    """Scrape opportunities via RSS and schedule them for posting"""
    print("\n🔍 Starting RSS feed collection...")
    
    # Get opportunities from RSS feeds
    all_opportunities = get_jobs_via_rss()
    
    if not all_opportunities:
        print("⚠️ No new opportunities found")
        return []
    
    print(f"\n📅 Scheduling {len(all_opportunities)} opportunities...")
    
    # Generate posting times
    posting_times = generate_posting_times(len(all_opportunities))
    
    # Create scheduled posts
    scheduled_posts = []
    for i, opp in enumerate(all_opportunities):
        if i >= len(posting_times):
            break
        
        if opp['type'] == 'job':
            tweet_text = format_job_tweet(opp)
        elif opp['type'] == 'scholarship':
            tweet_text = format_scholarship_tweet(opp)
        else:
            continue
        
        scheduled_posts.append({
            'scheduled_time': posting_times[i],
            'tweet_text': tweet_text,
            'url': opp['url'],
            'category': opp['type'],
            'posted': False
        })
        
        print(f"  ✓ Scheduled: {opp['title'][:60]}...")
        print(f"    Post time: {posting_times[i]}")
    
    # Mark today as scraped
    set_last_scrape_date(datetime.utcnow().strftime('%Y-%m-%d'))
    
    return scheduled_posts

def post_due_tweets(client):
    """Post tweets that are due now"""
    schedule = load_schedule()
    now = datetime.utcnow().isoformat() + 'Z'
    
    posted_count = 0
    
    for post in schedule:
        if not post['posted'] and post['scheduled_time'] <= now:
            try:
                print(f"\n📤 Posting: {post['tweet_text'][:80]}...")
                client.create_tweet(text=post['tweet_text'])
                post['posted'] = True
                save_posted_url(post['url'])
                posted_count += 1
                print(f"  ✓ Posted successfully!")
                time.sleep(5)  # Small delay between posts
            except Exception as e:
                print(f"  ✗ Error posting: {e}")
    
    # Remove posted tweets from schedule
    schedule = [p for p in schedule if not p['posted']]
    save_schedule(schedule)
    
    return posted_count

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main bot function"""
    print(f"\n{'='*70}")
    print(f"🤖 X Auto-Poster Bot - RSS Feed Edition")
    print(f"⏰ Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"🇳🇬 Nigeria time: {(datetime.utcnow() + timedelta(hours=1)).strftime('%H:%M:%S')} WAT")
    print(f"{'='*70}\n")
    
    # Authenticate with X
    client = authenticate_twitter()
    if not client:
        print("✗ Cannot proceed without X authentication")
        return
    
    # Load existing schedule
    schedule = load_schedule()
    print(f"📋 Current schedule has {len(schedule)} pending posts")
    
    # Check if we should scrape today
    if should_scrape_today():
        print("\n🆕 Time to collect fresh opportunities from RSS feeds!")
        new_posts = scrape_and_schedule()
        schedule.extend(new_posts)
        save_schedule(schedule)
        print(f"\n✅ Added {len(new_posts)} new posts to schedule")
    else:
        print("\n⏭️ Already collected opportunities today, skipping")
    
    # Post any due tweets
    print("\n📬 Checking for due posts...")
    posted_count = post_due_tweets(client)
    
    if posted_count > 0:
        print(f"\n🎉 Successfully posted {posted_count} tweet(s)!")
    else:
        print("\n⏳ No posts due right now")
        if schedule:
            next_post = min(schedule, key=lambda x: x['scheduled_time'])
            print(f"📅 Next post scheduled for: {next_post['scheduled_time']}")
    
    print(f"\n{'='*70}")
    print(f"✅ Bot run complete!")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
