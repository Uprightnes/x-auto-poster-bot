import tweepy
import requests
from bs4 import BeautifulSoup
import time
import random
import os
from datetime import datetime, timedelta
import json
import re

# ============================================================================
# CONFIGURATION
# ============================================================================

# X API Authentication (from GitHub Secrets)
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')

# File to store scheduled posts
SCHEDULE_FILE = 'scheduled_posts.json'
LAST_RUN_FILE = 'last_scrape_date.txt'

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
# SCRAPING FUNCTIONS
# ============================================================================

def extract_salary(text):
    """Extract salary information from text"""
    if not text:
        return None
    
    salary_patterns = [
        r'₦[\d,]+\s*-\s*₦[\d,]+',
        r'N[\d,]+\s*-\s*N[\d,]+',
        r'\$[\d,]+\s*-\s*\$[\d,]+',
        r'₦[\d,]+',
        r'\$[\d,]+',
    ]
    
    for pattern in salary_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group()
    return None

def extract_location_nigeria(text):
    """Extract Nigerian state/city from text"""
    if not text:
        return "Nigeria"
    
    nigerian_states = [
        'Lagos', 'Abuja', 'Port Harcourt', 'Kano', 'Ibadan', 'Kaduna',
        'Benin City', 'Enugu', 'Jos', 'Ilorin', 'Oyo', 'Abeokuta',
        'Calabar', 'Owerri', 'Warri', 'Uyo', 'Akure', 'Osogbo'
    ]
    
    text_lower = text.lower()
    for state in nigerian_states:
        if state.lower() in text_lower:
            return state
    
    return "Nigeria"

def scrape_jobberman_nigeria():
    """Scrape jobs from Jobberman Nigeria"""
    jobs = []
    try:
        url = "https://www.jobberman.com/jobs"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        job_listings = soup.find_all('article')[:5]
        
        for job in job_listings:
            try:
                title_elem = job.find('h3') or job.find('h2')
                link_elem = job.find('a', href=True)
                
                if title_elem and link_elem:
                    job_url = link_elem['href']
                    if not job_url.startswith('http'):
                        job_url = f"https://www.jobberman.com{job_url}"
                    
                    job_text = job.get_text()
                    company = "Nigerian Company"
                    company_elem = job.find('p', class_='text')
                    if company_elem:
                        company = company_elem.get_text(strip=True).split('•')[0].strip()
                    
                    location = extract_location_nigeria(job_text)
                    salary = extract_salary(job_text)
                    work_type = "Onsite"
                    if 'remote' in job_text.lower():
                        work_type = "Remote"
                    elif 'hybrid' in job_text.lower():
                        work_type = "Hybrid"
                    
                    jobs.append({
                        'title': title_elem.get_text(strip=True),
                        'company': company,
                        'url': job_url,
                        'location': location,
                        'salary': salary,
                        'work_type': work_type,
                        'type': 'job'
                    })
            except:
                continue
        
        print(f"✓ Found {len(jobs)} jobs on Jobberman")
    except Exception as e:
        print(f"✗ Error scraping Jobberman: {e}")
    
    return jobs

def scrape_myjobmag_nigeria():
    """Scrape jobs from MyJobMag Nigeria"""
    jobs = []
    try:
        url = "https://www.myjobmag.com/jobs-by-location/jobs-in-nigeria"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        job_listings = soup.find_all('div', class_='search-result')[:5]
        
        for job in job_listings:
            try:
                title_elem = job.find('h2') or job.find('a')
                link_elem = job.find('a', href=True)
                
                if title_elem and link_elem:
                    job_url = link_elem['href']
                    if not job_url.startswith('http'):
                        job_url = f"https://www.myjobmag.com{job_url}"
                    
                    job_text = job.get_text()
                    company = "Nigerian Company"
                    company_elem = job.find('p')
                    if company_elem:
                        company = company_elem.get_text(strip=True)
                    
                    location = extract_location_nigeria(job_text)
                    salary = extract_salary(job_text)
                    work_type = "Onsite"
                    if 'remote' in job_text.lower():
                        work_type = "Remote"
                    
                    jobs.append({
                        'title': title_elem.get_text(strip=True),
                        'company': company,
                        'url': job_url,
                        'location': location,
                        'salary': salary,
                        'work_type': work_type,
                        'type': 'job'
                    })
            except:
                continue
        
        print(f"✓ Found {len(jobs)} jobs on MyJobMag")
    except Exception as e:
        print(f"✗ Error scraping MyJobMag: {e}")
    
    return jobs

def scrape_remoteok_jobs():
    """Scrape remote jobs from RemoteOK"""
    jobs = []
    try:
        url = "https://remoteok.com/remote-jobs"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        job_listings = soup.find_all('tr', class_='job')[:3]
        
        for job in job_listings:
            try:
                title_elem = job.find('h2', itemprop='title')
                company_elem = job.find('h3', itemprop='name')
                link_elem = job.find('a', class_='preventLink')
                
                if title_elem and link_elem:
                    job_url = f"https://remoteok.com{link_elem['href']}"
                    job_text = job.get_text()
                    salary = extract_salary(job_text)
                    
                    jobs.append({
                        'title': title_elem.get_text(strip=True),
                        'company': company_elem.get_text(strip=True) if company_elem else 'Remote Company',
                        'url': job_url,
                        'location': 'Worldwide',
                        'salary': salary,
                        'work_type': 'Remote',
                        'type': 'job'
                    })
            except:
                continue
        
        print(f"✓ Found {len(jobs)} remote jobs")
    except Exception as e:
        print(f"✗ Error scraping RemoteOK: {e}")
    
    return jobs

def scrape_scholarships():
    """Scrape international scholarships"""
    scholarships = []
    try:
        url = "https://www.scholarshipportal.com/scholarships"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scholarship_listings = soup.find_all('div', class_='_scholarship')[:2]
        
        for scholarship in scholarship_listings:
            try:
                title_elem = scholarship.find('h3')
                link_elem = scholarship.find('a')
                
                if title_elem and link_elem:
                    scholarship_url = link_elem['href']
                    if not scholarship_url.startswith('http'):
                        scholarship_url = f"https://www.scholarshipportal.com{scholarship_url}"
                    
                    scholarship_text = scholarship.get_text()
                    
                    country = "International"
                    country_elem = scholarship.find('span', class_='country')
                    if country_elem:
                        country = country_elem.get_text(strip=True)
                    
                    level = []
                    if 'undergraduate' in scholarship_text.lower() or 'bachelor' in scholarship_text.lower():
                        level.append('Undergraduate')
                    if 'master' in scholarship_text.lower() or 'postgraduate' in scholarship_text.lower():
                        level.append('Masters')
                    if 'phd' in scholarship_text.lower() or 'doctorate' in scholarship_text.lower():
                        level.append('PhD')
                    
                    fully_funded = 'fully funded' in scholarship_text.lower() or 'full scholarship' in scholarship_text.lower()
                    
                    scholarships.append({
                        'title': title_elem.get_text(strip=True),
                        'url': scholarship_url,
                        'country': country,
                        'level': level if level else ['All Levels'],
                        'fully_funded': fully_funded,
                        'type': 'scholarship'
                    })
            except:
                continue
        
        print(f"✓ Found {len(scholarships)} scholarships")
    except Exception as e:
        print(f"✗ Error scraping scholarships: {e}")
    
    return scholarships

# ============================================================================
# FORMATTING FUNCTIONS
# ============================================================================

def format_job_tweet(job):
    """Format job as tweet text"""
    tweet = f"🔥 {job['title']}\n\n"
    tweet += f"Company: {job['company']}\n"
    tweet += f"Location: {job['location']}\n"
    tweet += f"Type: {job['work_type']}\n"
    
    if job.get('salary'):
        tweet += f"Salary: {job['salary']}\n"
    
    tweet += f"\nAPPLY HERE: {job['url']}"
    
    # Truncate if too long
    if len(tweet) > 280:
        available = 280 - len(job['url']) - 25
        tweet = f"🔥 {job['title'][:100]}\n\n"
        tweet += f"Company: {job['company']}\n"
        tweet += f"Location: {job['location']}\n"
        if job.get('salary'):
            tweet += f"Salary: {job['salary']}\n"
        tweet += f"\nAPPLY: {job['url']}"
    
    return tweet

def format_scholarship_tweet(scholarship):
    """Format scholarship as tweet text"""
    year = datetime.now().year
    title = scholarship['title']
    if str(year) not in title and str(year + 1) not in title:
        title = f"{title} {year + 1}"
    
    tweet = f"🎓 {title}"
    if scholarship['fully_funded']:
        tweet += " | Fully Funded"
    tweet += "\n\n"
    
    tweet += f"Scholarship For:\n"
    for level in scholarship['level']:
        tweet += f"* {level}\n"
    
    tweet += f"\nCountry: {scholarship['country']}\n"
    
    if scholarship['fully_funded']:
        tweet += f"\nBenefits:\n"
        tweet += f"* Full Tuition\n"
        tweet += f"* Stipends\n"
    
    tweet += f"\nAPPLY: {scholarship['url']}"
    
    # Truncate if too long
    if len(tweet) > 280:
        tweet = f"🎓 {title[:100]}"
        if scholarship['fully_funded']:
            tweet += " | Funded"
        tweet += f"\n\nFor: {', '.join(scholarship['level'])}\n"
        tweet += f"Country: {scholarship['country']}\n"
        tweet += f"\nAPPLY: {scholarship['url']}"
    
    return tweet

# ============================================================================
# SCHEDULING FUNCTIONS
# ============================================================================

def generate_posting_times(count=10):
    """Generate posting times throughout the day"""
    now = datetime.utcnow()
    times = []
    
    # Generate times: 7am, 9am, 11am, 1pm, 3pm, 5pm, 7pm, 9pm UTC
    # (Adjust these hours based on your timezone!)
    hours = [7, 9, 11, 13, 15, 17, 19, 21]
    
    for i in range(min(count, len(hours))):
        post_time = now.replace(hour=hours[i], minute=0, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for tomorrow
        if post_time < now:
            post_time += timedelta(days=1)
        
        times.append(post_time.isoformat() + 'Z')
    
    return times

def should_scrape_today():
    """Check if we should scrape for new jobs today"""
    last_scrape = get_last_scrape_date()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Scrape if we haven't scraped today OR if it's around 5am UTC
    current_hour = datetime.utcnow().hour
    
    if last_scrape != today and current_hour >= 5:
        return True
    
    return False

def scrape_and_schedule():
    """Scrape opportunities and schedule them for posting"""
    print("\n🔍 Starting scraping session...")
    
    all_opportunities = []
    
    print("📱 Scraping Nigerian job sites...")
    all_opportunities.extend(scrape_jobberman_nigeria())
    time.sleep(2)
    all_opportunities.extend(scrape_myjobmag_nigeria())
    time.sleep(2)
    
    print("\n🌍 Scraping international opportunities...")
    all_opportunities.extend(scrape_remoteok_jobs())
    time.sleep(2)
    all_opportunities.extend(scrape_scholarships())
    
    # Shuffle for variety
    random.shuffle(all_opportunities)
    
    # Take top 10
    opportunities = all_opportunities[:10]
    
    if not opportunities:
        print("⚠️ No new opportunities found")
        return []
    
    print(f"\n✓ Found {len(opportunities)} opportunities to schedule")
    
    # Generate posting times
    posting_times = generate_posting_times(len(opportunities))
    
    # Create scheduled posts
    scheduled_posts = []
    for i, opp in enumerate(opportunities):
        if i >= len(posting_times):
            break
        
        if opp['type'] == 'job':
            tweet_text = format_job_tweet(opp)
            category = "Job"
        elif opp['type'] == 'scholarship':
            tweet_text = format_scholarship_tweet(opp)
            category = "Scholarship"
        else:
            continue
        
        scheduled_posts.append({
            'scheduled_time': posting_times[i],
            'tweet_text': tweet_text,
            'url': opp['url'],
            'category': category,
            'posted': False
        })
        
        print(f"  ✓ Scheduled: {opp['title'][:50]}... for {posting_times[i]}")
    
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
                print(f"\n📤 Posting: {post['tweet_text'][:60]}...")
                client.create_tweet(text=post['tweet_text'])
                post['posted'] = True
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
    print(f"\n{'='*60}")
    print(f"🤖 X Auto-Poster Bot Running")
    print(f"⏰ Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}\n")
    
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
        print("\n🆕 Time to scrape for new opportunities!")
        new_posts = scrape_and_schedule()
        schedule.extend(new_posts)
        save_schedule(schedule)
        print(f"\n✓ Added {len(new_posts)} new posts to schedule")
    else:
        print("\n⏭️ Already scraped today, skipping scraping")
    
    # Post any due tweets
    print("\n📬 Checking for due posts...")
    posted_count = post_due_tweets(client)
    
    if posted_count > 0:
        print(f"\n✅ Posted {posted_count} tweet(s)")
    else:
        print("\n⏳ No posts due right now")
    
    print(f"\n{'='*60}")
    print(f"✅ Bot run complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
