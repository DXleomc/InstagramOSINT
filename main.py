import argparse
import json
import os
import random
import string
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Union
import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

# Import banner if available, otherwise create a simple one
try:
    from banner import banner
except ImportError:
    banner = """
    #############################################
    #         INSTAGRAM OSINT TOOL             #
    #           - Advanced Edition -           #
    #############################################
    """


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
    """Advanced Instagram OSINT tool with improved functionality"""

    def __init__(self, username: str, download_photos: bool = False, verbose: bool = False):
        """
        Initialize the Instagram OSINT tool
        
        Args:
            username (str): Instagram username to investigate
            download_photos (bool): Whether to download photos
            verbose (bool): Enable verbose logging
        """
        self.username = username.lower().strip()
        self.download_photos = download_photos
        self.verbose = verbose
        self.session = requests.Session()
        self.profile_data = {}
        self.logger = self._setup_logger()
        
        # Updated user agents
        self.useragents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36'
        ]
        
        # Rate limiting control
        self.last_request_time = 0
        self.min_request_interval = 2  # seconds between requests
        
        # Create output directory
        self.output_dir = self._create_output_directory()
        
        # Run the scan
        self.scan_profile()

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
            response = self.session.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if retry_count < 3:  # Max 3 retries
                self.logger.warning(f"Request failed (attempt {retry_count + 1}/3): {str(e)}")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(url, retry_count + 1)
            self.logger.error(f"Failed to fetch {url} after 3 attempts")
            return None

    def _create_output_directory(self) -> str:
        """Create output directory for scan results"""
        base_dir = os.path.join(os.getcwd(), "instagram_osint_results")
        os.makedirs(base_dir, exist_ok=True)
        
        output_dir = os.path.join(base_dir, self.username)
        counter = 1
        
        while os.path.exists(output_dir):
            output_dir = os.path.join(base_dir, f"{self.username}_{counter}")
            counter += 1
            
        os.makedirs(output_dir)
        return output_dir

    def scan_profile(self) -> None:
        """Main method to scan Instagram profile"""
        self.logger.info(f"Starting scan for username: {self.username}")
        
        # Get profile data
        if not self._fetch_profile_data():
            self.logger.error("Failed to fetch profile data")
            sys.exit(1)
            
        # Save data
        self._save_data()
        
        # Download photos if requested
        if self.download_photos:
            self._download_content()
            
        # Print results
        self._print_results()

    def _fetch_profile_data(self) -> bool:
        """Fetch and parse Instagram profile data"""
        url = f'https://www.instagram.com/{self.username}/'
        response = self._make_request(url)
        
        if not response:
            return False
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the tags that hold the data
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
                "username": user_data.get('username'),
                "profile_name": self.description.get('name', '') if self.description else user_data.get('full_name', ''),
                "url": self.description.get('mainEntityofPage', {}).get('@id', '') if self.description else f"https://www.instagram.com/{self.username}/",
                "followers": text[0] if len(text) > 0 else str(user_data.get('edge_followed_by', {}).get('count', 'N/A')),
                "following": text[2] if len(text) > 2 else str(user_data.get('edge_follow', {}).get('count', 'N/A')),
                "posts": text[4] if len(text) > 4 else str(user_data.get('edge_owner_to_timeline_media', {}).get('count', 'N/A')),
                "bio": user_data.get('biography', ''),
                "profile_pic_url": user_data.get('profile_pic_url_hd', user_data.get('profile_pic_url', '')),
                "is_business_account": user_data.get('is_business_account', False),
                "connected_to_facebook": user_data.get('connected_fb_page', None),
                "external_url": user_data.get('external_url', ''),
                "joined_recently": user_data.get('is_joined_recently', False),
                "business_category": user_data.get('business_category_name', ''),
                "is_private": user_data.get('is_private', False),
                "is_verified": user_data.get('is_verified', False),
                "has_guides": user_data.get('has_guides', False),
                "has_clips": user_data.get('has_clips', False),
                "has_ar_effects": user_data.get('has_ar_effects', False),
                "has_channel": user_data.get('has_channel', False),
                "highlight_reel_count": user_data.get('highlight_reel_count', 0),
                "scraped_timestamp": datetime.now().isoformat()
            }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error parsing profile data: {str(e)}", exc_info=self.verbose)
            return False

    def _download_content(self) -> None:
        """Download profile content (photos, etc.)"""
        if self.profile_data.get('is_private', True):
            self.logger.warning("Cannot download content from private profile")
            return
            
        # Download profile picture
        self._download_profile_picture()
        
        # Download posts if not private
        self._download_posts()

    def _download_profile_picture(self) -> None:
        """Download the profile picture"""
        pic_url = self.profile_data.get('profile_pic_url')
        if not pic_url:
            return
            
        try:
            response = self._make_request(pic_url)
            if response:
                filename = os.path.join(self.output_dir, f"{self.username}_profile_pic.jpg")
                with open(filename, 'wb') as f:
                    f.write(response.content)
                self.logger.info(f"Downloaded profile picture to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to download profile picture: {str(e)}")

    def _download_posts(self, limit: int = 12) -> None:
        """Download recent posts"""
        try:
            edges = self.profile_meta['entry_data']['ProfilePage'][0]['graphql']['user'][
                'edge_owner_to_timeline_media']['edges'][:limit]
                
            posts_dir = os.path.join(self.output_dir, "posts")
            os.makedirs(posts_dir, exist_ok=True)
            
            posts_data = []
            
            for index, post in enumerate(edges):
                post_node = post['node']
                post_id = post_node['id']
                
                # Create post metadata
                post_data = {
                    "id": post_id,
                    "caption": post_node.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                    "comments_count": post_node.get('edge_media_to_comment', {}).get('count', 0),
                    "likes_count": post_node.get('edge_liked_by', {}).get('count', 0),
                    "timestamp": post_node.get('taken_at_timestamp', 0),
                    "is_video": post_node.get('is_video', False),
                    "shortcode": post_node.get('shortcode', ''),
                    "display_url": post_node.get('display_url', '')
                }
                posts_data.append(post_data)
                
                # Download the media
                media_url = post_node.get('display_url')
                if media_url:
                    try:
                        response = self._make_request(media_url)
                        if response:
                            ext = 'mp4' if post_data['is_video'] else 'jpg'
                            filename = os.path.join(posts_dir, f"{post_id}.{ext}")
                            with open(filename, 'wb') as f:
                                f.write(response.content)
                            self.logger.debug(f"Downloaded post {post_id}")
                    except Exception as e:
                        self.logger.error(f"Failed to download post {post_id}: {str(e)}")
                
                # Add delay between downloads
                time.sleep(random.uniform(1, 3))
            
            # Save posts metadata
            with open(os.path.join(posts_dir, 'posts_metadata.json'), 'w') as f:
                json.dump(posts_data, f, indent=2)
                
            self.logger.info(f"Downloaded {len(posts_data)} posts")
            
        except Exception as e:
            self.logger.error(f"Error downloading posts: {str(e)}", exc_info=self.verbose)

    def _save_data(self) -> None:
        """Save all collected data to files"""
        try:
            # Save profile data
            with open(os.path.join(self.output_dir, 'profile_data.json'), 'w') as f:
                json.dump(self.profile_data, f, indent=2)
            
            self.logger.info(f"Data saved to directory: {self.output_dir}")
        except Exception as e:
            self.logger.error(f"Failed to save data: {str(e)}")

    def _print_results(self) -> None:
        """Print results in a readable format"""
        print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}{'Instagram Profile Report':^60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        
        print(f"{Colors.BOLD}Username:{Colors.ENDC} {self.profile_data.get('username')}")
        print(f"{Colors.BOLD}Profile Name:{Colors.ENDC} {self.profile_data.get('profile_name')}")
        print(f"{Colors.BOLD}URL:{Colors.ENDC} {self.profile_data.get('url')}")
        print(f"{Colors.BOLD}Followers:{Colors.ENDC} {self.profile_data.get('followers')}")
        print(f"{Colors.BOLD}Following:{Colors.ENDC} {self.profile_data.get('following')}")
        print(f"{Colors.BOLD}Posts:{Colors.ENDC} {self.profile_data.get('posts')}")
        
        print(f"\n{Colors.BOLD}Bio:{Colors.ENDC}")
        print(self.profile_data.get('bio', 'No bio available'))
        
        if self.profile_data.get('external_url'):
            print(f"\n{Colors.BOLD}External URL:{Colors.ENDC} {self.profile_data.get('external_url')}")
        
        print(f"\n{Colors.BOLD}Account Type:{Colors.ENDC}")
        print(f"Business Account: {'Yes' if self.profile_data.get('is_business_account') else 'No'}")
        if self.profile_data.get('is_business_account'):
            print(f"Business Category: {self.profile_data.get('business_category', 'N/A')}")
        print(f"Private Account: {'Yes' if self.profile_data.get('is_private') else 'No'}")
        print(f"Verified Account: {'Yes' if self.profile_data.get('is_verified') else 'No'}")
        print(f"Connected to Facebook: {'Yes' if self.profile_data.get('connected_to_facebook') else 'No'}")
        
        print(f"\n{Colors.BOLD}Additional Features:{Colors.ENDC}")
        print(f"Has Guides: {'Yes' if self.profile_data.get('has_guides') else 'No'}")
        print(f"Has Clips: {'Yes' if self.profile_data.get('has_clips') else 'No'}")
        print(f"Has AR Effects: {'Yes' if self.profile_data.get('has_ar_effects') else 'No'}")
        print(f"Has Channel: {'Yes' if self.profile_data.get('has_channel') else 'No'}")
        print(f"Highlight Reels: {self.profile_data.get('highlight_reel_count', 0)}")
        
        print(f"\n{Colors.BOLD}Scraped At:{Colors.ENDC} {self.profile_data.get('scraped_timestamp')}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Advanced Instagram OSINT Tool")
    parser.add_argument("username", help="Instagram username to investigate")
    parser.add_argument("--download", "-d", help="Download profile photos", action="store_true")
    parser.add_argument("--verbose", "-v", help="Enable verbose output", action="store_true")
    return parser.parse_args()


def main():
    """Main function"""
    print(f"{Colors.OKBLUE}{banner}{Colors.ENDC}")
    
    args = parse_args()
    
    try:
        tool = InstagramOSINT(
            username=args.username,
            download_photos=args.download,
            verbose=args.verbose
        )
    except Exception as e:
        print(f"{Colors.FAIL}Error: {str(e)}{Colors.ENDC}")
        sys.exit(1)


if __name__ == '__main__':
    main()
