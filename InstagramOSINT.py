from bs4 import BeautifulSoup
import json
import os
import requests
import random
import string
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Union
import logging
from urllib.parse import urlparse
import argparse


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class InstagramOSINT:
    """Instagram OSINT tool for gathering public profile information"""
    
    def __init__(self, username: str, verbose: bool = False, max_retries: int = 3):
        """
        Initialize the Instagram OSINT tool
        
        Args:
            username (str): Instagram username to investigate
            verbose (bool): Enable verbose logging
            max_retries (int): Maximum number of retries for failed requests
        """
        self.username = username.lower().strip()
        self.verbose = verbose
        self.max_retries = max_retries
        self.session = requests.Session()
        self.profile_data = {}
        self.logger = self._setup_logger()
        
        # Updated user agents
        self.useragents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
        ]
        
        # Rate limiting control
        self.last_request_time = 0
        self.min_request_interval = 2  # seconds between requests
        
        self.scrape_profile()

    def _setup_logger(self) -> logging.Logger:
        """Configure logging"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, url: str, retry_count: int = 0) -> Optional[requests.Response]:
        """Make HTTP request with rate limiting and retries"""
        self._rate_limit()
        
        headers = {
            'User-Agent': random.choice(self.useragents),
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'DNT': '1',  # Do Not Track
        }
        
        try:
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                self.logger.warning(f"Request failed (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(url, retry_count + 1)
            self.logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
            return None

    def __repr__(self) -> str:
        return f"InstagramOSINT(username='{self.username}')"

    def __str__(self) -> str:
        return f"Instagram OSINT tool for username: {self.username}"

    def __getitem__(self, key: str) -> Union[str, int, bool]:
        return self.profile_data.get(key, None)

    def scrape_profile(self) -> Optional[Dict]:
        """
        Scrape Instagram profile data
        
        Returns:
            dict: Profile data if successful, None otherwise
        """
        url = f'https://www.instagram.com/{self.username}/'
        response = self._make_request(url)
        
        if not response:
            self.logger.error(f"Failed to fetch profile for username: {self.username}")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the tags that hold the data we want to parse
        general_data = soup.find_all('meta', attrs={'property': 'og:description'})
        more_data = soup.find_all('script', attrs={'type': 'text/javascript'})
        description = soup.find('script', attrs={'type': 'application/ld+json'})
        
        try:
            if not general_data:
                raise ValueError("No general profile data found")
                
            text = general_data[0].get('content').split()
            self.description = json.loads(description.get_text()) if description else {}
            
            # Find the correct script tag containing profile data
            profile_script = None
            for script in more_data:
                if script.string and 'window._sharedData' in script.string:
                    profile_script = script.string
                    break
                    
            if not profile_script:
                raise ValueError("Profile data script not found")
                
            # Clean and parse the JavaScript data
            json_data = profile_script.strip().split(' = ', 1)[1].rstrip(';')
            self.profile_meta = json.loads(json_data)
            
            user_data = self.profile_meta['entry_data']['ProfilePage'][0]['graphql']['user']
            
            # Enhanced data extraction
            self.profile_data = {
                "Username": user_data.get('username'),
                "Profile Name": self.description.get('name', '') if self.description else user_data.get('full_name', ''),
                "URL": self.description.get('mainEntityofPage', {}).get('@id', '') if self.description else f"https://www.instagram.com/{self.username}/",
                "Followers": text[0] if len(text) > 0 else str(user_data.get('edge_followed_by', {}).get('count', 'N/A')),
                "Following": text[2] if len(text) > 2 else str(user_data.get('edge_follow', {}).get('count', 'N/A')),
                "Posts": text[4] if len(text) > 4 else str(user_data.get('edge_owner_to_timeline_media', {}).get('count', 'N/A')),
                "Bio": user_data.get('biography', ''),
                "Profile Picture URL": user_data.get('profile_pic_url_hd', user_data.get('profile_pic_url', '')),
                "Is Business Account": user_data.get('is_business_account', False),
                "Connected to Facebook": user_data.get('connected_fb_page', None),
                "External URL": user_data.get('external_url', ''),
                "Joined Recently": user_data.get('is_joined_recently', False),
                "Business Category": user_data.get('business_category_name', ''),
                "Is Private": user_data.get('is_private', False),
                "Is Verified": user_data.get('is_verified', False),
                "Has Guides": user_data.get('has_guides', False),
                "Has Clips": user_data.get('has_clips', False),
                "Has AR Effects": user_data.get('has_ar_effects', False),
                "Has Channel": user_data.get('has_channel', False),
                "Highlight Reel Count": user_data.get('highlight_reel_count', 0),
                "Scraped Timestamp": datetime.now().isoformat()
            }
            
            self.logger.info(f"Successfully scraped profile for {self.username}")
            return self.profile_data
            
        except Exception as e:
            self.logger.error(f"Error scraping profile: {str(e)}", exc_info=self.verbose)
            return None

    def scrape_posts(self, limit: int = 12) -> Optional[Dict]:
        """
        Scrape recent posts from the profile
        
        Args:
            limit (int): Maximum number of posts to scrape
            
        Returns:
            dict: Dictionary of post data if successful, None otherwise
        """
        if not self.profile_data:
            self.logger.error("No profile data available")
            return None
            
        if self.profile_data.get('Is Private', True):
            self.logger.warning("Cannot scrape posts from a private profile")
            return None
            
        posts = {}
        try:
            edges = self.profile_meta['entry_data']['ProfilePage'][0]['graphql']['user'][
                'edge_owner_to_timeline_media']['edges'][:limit]
                
            for index, post in enumerate(edges):
                post_node = post['node']
                post_id = post_node['id']
                
                posts[post_id] = {
                    "Caption": post_node.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                    "Comments Count": post_node.get('edge_media_to_comment', {}).get('count', 0),
                    "Comments Disabled": post_node.get('comments_disabled', False),
                    "Timestamp": post_node.get('taken_at_timestamp', 0),
                    "Date": datetime.fromtimestamp(post_node.get('taken_at_timestamp', 0)).isoformat(),
                    "Likes Count": post_node.get('edge_liked_by', {}).get('count', 0),
                    "Location": post_node.get('location', {}),
                    "Accessibility Caption": post_node.get('accessibility_caption', ''),
                    "Is Video": post_node.get('is_video', False),
                    "Video Views": post_node.get('video_view_count', 0) if post_node.get('is_video', False) else None,
                    "Shortcode": post_node.get('shortcode', ''),
                    "Dimensions": post_node.get('dimensions', {}),
                    "Display URL": post_node.get('display_url', ''),
                    "Thumbnail Resources": post_node.get('thumbnail_resources', []),
                    "Post URL": f"https://www.instagram.com/p/{post_node.get('shortcode', '')}/"
                }
                
            self.logger.info(f"Scraped {len(posts)} posts for {self.username}")
            return posts
            
        except Exception as e:
            self.logger.error(f"Error scraping posts: {str(e)}", exc_info=self.verbose)
            return None

    def download_media(self, output_dir: str = None, limit: int = 12) -> bool:
        """
        Download profile picture and recent posts
        
        Args:
            output_dir (str): Directory to save files (default: username)
            limit (int): Maximum number of posts to download
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.profile_data:
            self.logger.error("No profile data available")
            return False
            
        # Create output directory
        output_dir = output_dir or self.username
        os.makedirs(output_dir, exist_ok=True)
        
        # Download profile picture
        profile_pic_url = self.profile_data.get('Profile Picture URL')
        if profile_pic_url:
            try:
                response = self._make_request(profile_pic_url)
                if response:
                    filename = os.path.join(output_dir, f"{self.username}_profile_pic.jpg")
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    self.logger.info(f"Downloaded profile picture to {filename}")
            except Exception as e:
                self.logger.error(f"Failed to download profile picture: {str(e)}")
        
        # Download posts if not private
        if not self.profile_data.get('Is Private', True):
            posts = self.scrape_posts(limit=limit)
            if posts:
                posts_dir = os.path.join(output_dir, "posts")
                os.makedirs(posts_dir, exist_ok=True)
                
                # Save posts metadata
                with open(os.path.join(posts_dir, 'posts_metadata.json'), 'w') as f:
                    json.dump(posts, f, indent=2)
                
                # Download each post's media
                for post_id, post_data in posts.items():
                    try:
                        media_url = post_data.get('Display URL')
                        if not media_url:
                            continue
                            
                        response = self._make_request(media_url)
                        if response:
                            ext = 'mp4' if post_data.get('Is Video') else 'jpg'
                            filename = os.path.join(posts_dir, f"{post_id}.{ext}")
                            with open(filename, 'wb') as f:
                                f.write(response.content)
                            self.logger.debug(f"Downloaded post {post_id} to {filename}")
                    except Exception as e:
                        self.logger.error(f"Failed to download post {post_id}: {str(e)}")
        
        return True

    def save_data(self, output_dir: str = None) -> bool:
        """
        Save all collected data to files
        
        Args:
            output_dir (str): Directory to save files (default: username)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.profile_data:
            self.logger.error("No data to save")
            return False
            
        output_dir = output_dir or self.username
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Save profile data
            with open(os.path.join(output_dir, 'profile_data.json'), 'w') as f:
                json.dump(self.profile_data, f, indent=2)
            
            # Save posts data if available
            if not self.profile_data.get('Is Private', True):
                posts = self.scrape_posts()
                if posts:
                    with open(os.path.join(output_dir, 'posts_data.json'), 'w') as f:
                        json.dump(posts, f, indent=2)
            
            self.logger.info(f"Data saved to directory: {os.path.abspath(output_dir)}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save data: {str(e)}")
            return False

    def print_profile_data(self) -> None:
        """Print profile data in a readable format"""
        if not self.profile_data:
            print(f"{Colors.FAIL}No profile data available{Colors.ENDC}")
            return
            
        print(f"{Colors.HEADER}{'='*50}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}{'Instagram Profile Report':^50}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*50}{Colors.ENDC}")
        print(f"{Colors.BOLD}Username:{Colors.ENDC} {self.profile_data.get('Username')}")
        print(f"{Colors.BOLD}Profile Name:{Colors.ENDC} {self.profile_data.get('Profile Name')}")
        print(f"{Colors.BOLD}URL:{Colors.ENDC} {self.profile_data.get('URL')}")
        print(f"{Colors.BOLD}Followers:{Colors.ENDC} {self.profile_data.get('Followers')}")
        print(f"{Colors.BOLD}Following:{Colors.ENDC} {self.profile_data.get('Following')}")
        print(f"{Colors.BOLD}Posts:{Colors.ENDC} {self.profile_data.get('Posts')}")
        print(f"\n{Colors.BOLD}Bio:{Colors.ENDC}\n{self.profile_data.get('Bio')}")
        
        if self.profile_data.get('External URL'):
            print(f"\n{Colors.BOLD}External URL:{Colors.ENDC} {self.profile_data.get('External URL')}")
        
        print(f"\n{Colors.BOLD}Business Account:{Colors.ENDC} {'Yes' if self.profile_data.get('Is Business Account') else 'No'}")
        if self.profile_data.get('Is Business Account'):
            print(f"{Colors.BOLD}Business Category:{Colors.ENDC} {self.profile_data.get('Business Category')}")
        
        print(f"{Colors.BOLD}Private Account:{Colors.ENDC} {'Yes' if self.profile_data.get('Is Private') else 'No'}")
        print(f"{Colors.BOLD}Verified Account:{Colors.ENDC} {'Yes' if self.profile_data.get('Is Verified') else 'No'}")
        print(f"{Colors.BOLD}Connected to Facebook:{Colors.ENDC} {'Yes' if self.profile_data.get('Connected to Facebook') else 'No'}")
        
        print(f"\n{Colors.BOLD}Additional Features:{Colors.ENDC}")
        print(f"Has Guides: {'Yes' if self.profile_data.get('Has Guides') else 'No'}")
        print(f"Has Clips: {'Yes' if self.profile_data.get('Has Clips') else 'No'}")
        print(f"Has AR Effects: {'Yes' if self.profile_data.get('Has AR Effects') else 'No'}")
        print(f"Has Channel: {'Yes' if self.profile_data.get('Has Channel') else 'No'}")
        print(f"Highlight Reels: {self.profile_data.get('Highlight Reel Count')}")
        
        print(f"\n{Colors.BOLD}Scraped At:{Colors.ENDC} {self.profile_data.get('Scraped Timestamp')}")
        print(f"{Colors.HEADER}{'='*50}{Colors.ENDC}")


def main():
    """Command-line interface for the Instagram OSINT tool"""
    parser = argparse.ArgumentParser(description='Instagram OSINT Tool')
    parser.add_argument('username', help='Instagram username to investigate')
    parser.add_argument('-o', '--output', help='Output directory for saved data')
    parser.add_argument('-d', '--download', action='store_true', help='Download profile picture and posts')
    parser.add_argument('-l', '--limit', type=int, default=12, help='Limit number of posts to download (default: 12)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    
    tool = InstagramOSINT(args.username, verbose=args.verbose)
    
    if not tool.profile_data:
        print(f"{Colors.FAIL}Failed to retrieve data for {args.username}{Colors.ENDC}")
        sys.exit(1)
    
    tool.print_profile_data()
    
    if args.download:
        tool.download_media(output_dir=args.output, limit=args.limit)
    
    if args.output and not args.download:
        tool.save_data(output_dir=args.output)


if __name__ == '__main__':
    main()
