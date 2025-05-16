import requests
import datetime
import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import UserToken, Video, Playlist

logger = logging.getLogger(__name__)

class YouTubeAPI:
    """
    Utility class for interacting with the YouTube API
    """
    # YouTube API endpoints
    TOKEN_URL = 'https://oauth2.googleapis.com/token'
    WATCH_LATER_PLAYLIST_ID = 'WL'  # YouTube's Watch Later playlist ID
    
    def __init__(self, user=None, user_token=None):
        """
        Initialize with either a user or a user_token
        """
        if user:
            try:
                self.user_token = UserToken.objects.get(user=user)
            except UserToken.DoesNotExist:
                self.user_token = None
        else:
            self.user_token = user_token
            
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    @staticmethod
    def get_auth_url():
        """
        Generate the authorization URL for Google OAuth
        """
        # Add multiple scopes
        scopes = [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/drive.file"  # For creating/updating files in Drive
        ]
        
        # URL encode the scopes
        import urllib.parse
        scope = urllib.parse.quote(' '.join(scopes))
        
        client_id = settings.GOOGLE_CLIENT_ID
        redirect_uri = settings.GOOGLE_REDIRECT_URI
        
        # Add additional parameters to ensure we get the refresh token
        return (
            f"https://accounts.google.com/o/oauth2/auth"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope}"
            f"&response_type=code"
            f"&access_type=offline"
            f"&prompt=consent"  # Force to get refresh token
            f"&include_granted_scopes=true"
        )
    
    def exchange_code_for_tokens(self, code):
        """
        Exchange the authorization code for access and refresh tokens
        """
        payload = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        response = requests.post(self.TOKEN_URL, data=payload)
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            return None
        
        token_data = response.json()
        return token_data
    
    def refresh_access_token(self):
        """
        Refresh the access token using the refresh token
        """
        if not self.user_token or not self.user_token.refresh_token:
            logger.error("No refresh token available")
            return False
            
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.user_token.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(self.TOKEN_URL, data=payload)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            return False
            
        token_data = response.json()
        
        # Update the stored tokens
        self.user_token.access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)  # Default to 1 hour
        self.user_token.expires_at = timezone.now() + datetime.timedelta(seconds=expires_in)
        self.user_token.save()
        
        return True
    
    def ensure_valid_token(self):
        """
        Ensure the access token is valid, refreshing if needed
        """
        if not self.user_token:
            logger.error("No user token available")
            return False
            
        # Check if token is expired or will expire in the next 5 minutes
        if self.user_token.expires_at <= timezone.now() + datetime.timedelta(minutes=5):
            return self.refresh_access_token()
            
        return True
    
    def get_watch_later_videos(self):
        """
        Fetch videos from the user's Watch Later playlist
        """
        logger.info("Attempting to fetch Watch Later videos")
        
        if not self.ensure_valid_token():
            logger.error("Failed to ensure valid token")
            return None
            
        base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            'part': 'snippet,contentDetails',
            'playlistId': self.WATCH_LATER_PLAYLIST_ID,
            'maxResults': 50
        }
        headers = {
            'Authorization': f'Bearer {self.user_token.access_token}'
        }
        
        all_items = []
        next_page_token = None
        
        try:
            # First, check if we can actually access the Watch Later playlist
            response = requests.get(base_url, params=params, headers=headers)
            
            # Log the full response for debugging
            logger.info(f"Watch Later API response status: {response.status_code}")
            logger.debug(f"Watch Later API response: {response.text[:200]}...")
            
            if response.status_code == 403:
                logger.error("Access to Watch Later playlist is forbidden. This is a common limitation with the YouTube API.")
                logger.info("The YouTube API does not allow access to the Watch Later playlist for privacy reasons.")
                return []
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch Watch Later videos: {response.text}")
                return None
            
            data = response.json()
            items = data.get('items', [])
            logger.info(f"First page has {len(items)} items")
            all_items.extend(items)
            
            next_page_token = data.get('nextPageToken')
            page_count = 1
            
            while next_page_token:
                page_count += 1
                logger.info(f"Fetching page {page_count} of Watch Later videos")
                params['pageToken'] = next_page_token
                
                response = requests.get(base_url, params=params, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch page {page_count} of Watch Later videos: {response.text}")
                    break
                
                data = response.json()
                items = data.get('items', [])
                logger.info(f"Page {page_count} has {len(items)} items")
                all_items.extend(items)
                
                next_page_token = data.get('nextPageToken')
            
            logger.info(f"Total videos fetched from Watch Later: {len(all_items)}")
            return all_items
            
        except Exception as e:
            logger.exception(f"Exception while fetching Watch Later videos: {str(e)}")
            return None
    
    def sync_videos_for_user(self):
        """
        Sync the user's videos with our database
        """
        if not self.user_token:
            logger.error("No user token available")
            return False
            
        logger.info(f"Starting video sync for user: {self.user_token.user.username}")
        
        # First sync user playlists
        self.sync_user_playlists()
        
        # Sync liked videos
        self._sync_liked_videos()
        
        # Sync watch later videos
        self._sync_watch_later_videos()
        
        return True

    def _sync_playlist_videos(self, playlist_id, playlist_name):
        """Sync videos from a specific playlist"""
        logger.info(f"Syncing videos from playlist: {playlist_name} (ID: {playlist_id})")
        
        base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            'part': 'snippet,contentDetails',
            'playlistId': playlist_id,
            'maxResults': 50
        }
        headers = {
            'Authorization': f'Bearer {self.user_token.access_token}'
        }
        
        try:
            response = requests.get(base_url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch playlist videos: {response.text}")
                return False
            
            data = response.json()
            items = data.get('items', [])
            
            for item in items:
                try:
                    snippet = item.get('snippet', {})
                    video_id = snippet.get('resourceId', {}).get('videoId')
                    
                    if not video_id:
                        continue
                        
                    # Create or update video
                    video, created = Video.objects.update_or_create(
                        user=self.user_token.user,
                        video_id=video_id,
                        defaults={
                            'title': snippet.get('title', 'Untitled Video'),
                            'description': snippet.get('description', ''),
                            'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                            'published_at': datetime.datetime.fromisoformat(
                                snippet.get('publishedAt').replace('Z', '+00:00')
                            ),
                            'youtube_description': snippet.get('description', ''),
                            'channel_title': snippet.get('channelTitle', 'Unknown Channel'),
                            'channel_id': snippet.get('channelId', ''),
                            'playlist_id': playlist_id,
                            'playlist_name': playlist_name
                        }
                    )
                    
                    if created:
                        logger.info(f"Added playlist video: {snippet.get('title')}")
                    
                except Exception as e:
                    logger.error(f"Error processing playlist video: {str(e)}")
                    continue
                
            return True
            
        except Exception as e:
            logger.exception(f"Exception while fetching playlist videos: {str(e)}")
            return False

    def _sync_liked_videos(self):
        """Sync liked videos for a user"""
        logger.info("Syncing liked videos")
        
        liked_videos_url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            'part': 'snippet,contentDetails',
            'myRating': 'like',
            'maxResults': 50
        }
        headers = {
            'Authorization': f'Bearer {self.user_token.access_token}'
        }
        
        try:
            # Get all currently liked videos from our database
            existing_liked_videos = Video.objects.filter(
                user=self.user_token.user,
                is_liked=True
            ).values_list('video_id', flat=True)
            existing_liked_videos = set(existing_liked_videos)
            logger.info(f"Found {len(existing_liked_videos)} existing liked videos in database")
            
            # Track which videos are still liked
            currently_liked_videos = set()
            
            # Fetch all pages of liked videos
            all_items = []
            next_page_token = None
            
            # First page
            response = requests.get(liked_videos_url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch liked videos: {response.text}")
                return False
            
            data = response.json()
            items = data.get('items', [])
            all_items.extend(items)
            next_page_token = data.get('nextPageToken')
            
            # Fetch additional pages if available
            page_count = 1
            while next_page_token:
                page_count += 1
                logger.info(f"Fetching page {page_count} of liked videos")
                params['pageToken'] = next_page_token
                
                response = requests.get(liked_videos_url, params=params, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch page {page_count} of liked videos: {response.text}")
                    break
                
                data = response.json()
                items = data.get('items', [])
                all_items.extend(items)
                
                next_page_token = data.get('nextPageToken')
            
            logger.info(f"Total liked videos fetched from YouTube: {len(all_items)}")
            
            # Process all liked videos
            for video in all_items:
                try:
                    video_id = video.get('id')
                    snippet = video.get('snippet', {})
                    
                    if not video_id:
                        continue
                    
                    # Add to the set of currently liked videos
                    currently_liked_videos.add(video_id)
                        
                    # Create or update video
                    video_obj, created = Video.objects.update_or_create(
                        user=self.user_token.user,
                        video_id=video_id,
                        defaults={
                            'title': snippet.get('title', 'Untitled Video'),
                            'description': snippet.get('description', ''),
                            'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                            'published_at': datetime.datetime.fromisoformat(
                                snippet.get('publishedAt').replace('Z', '+00:00')
                            ),
                            'youtube_description': snippet.get('description', ''),
                            'channel_title': snippet.get('channelTitle', 'Unknown Channel'),
                            'channel_id': snippet.get('channelId', ''),
                            'is_liked': True
                        }
                    )
                    
                    if created:
                        logger.info(f"Added new liked video: {snippet.get('title')}")
                    else:
                        # Make sure it's marked as liked
                        if not video_obj.is_liked:
                            video_obj.is_liked = True
                            video_obj.save(update_fields=['is_liked'])
                            logger.info(f"Marked existing video as liked: {snippet.get('title')}")
                    
                except Exception as e:
                    logger.error(f"Error processing liked video {video_id if 'video_id' in locals() else 'unknown'}: {str(e)}")
                    continue
            
            # Find videos that were unliked
            unliked_videos = existing_liked_videos - currently_liked_videos
            if unliked_videos:
                logger.info(f"Found {len(unliked_videos)} videos that are no longer liked")
                # Update videos that are no longer liked
                Video.objects.filter(
                    user=self.user_token.user,
                    video_id__in=unliked_videos
                ).update(is_liked=False)
            
            return True
            
        except Exception as e:
            logger.exception(f"Exception while fetching liked videos: {str(e)}")
            return False

    def _sync_watch_history(self):
        """Attempt to sync watch history"""
        logger.info("Attempting to sync watch history (note: this may not work due to API limitations)")
        
        # Watch history isn't directly available via the API, but we can try to access it
        # as a special case playlist with ID 'HL'
        history_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            'part': 'snippet,contentDetails',
            'playlistId': 'HL',  # History playlist ID
            'maxResults': 50
        }
        headers = {
            'Authorization': f'Bearer {self.user_token.access_token}'
        }
        
        try:
            response = requests.get(history_url, params=params, headers=headers)
            
            # Most likely this will fail with a 403 or 404
            if response.status_code != 200:
                logger.warning(f"Could not access watch history: {response.status_code}")
                logger.warning("This is expected due to YouTube API limitations")
                return False
            
            data = response.json()
            items = data.get('items', [])
            
            for item in items:
                try:
                    snippet = item.get('snippet', {})
                    video_id = snippet.get('resourceId', {}).get('videoId')
                    
                    if not video_id:
                        continue
                        
                    # Create or update video
                    video_obj, created = Video.objects.update_or_create(
                        user=self.user_token.user,
                        video_id=video_id,
                        defaults={
                            'title': snippet.get('title', 'Untitled Video'),
                            'description': snippet.get('description', ''),
                            'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                            'published_at': datetime.datetime.fromisoformat(
                                snippet.get('publishedAt').replace('Z', '+00:00')
                            ),
                            'youtube_description': snippet.get('description', ''),
                            'channel_title': snippet.get('channelTitle', 'Unknown Channel'),
                            'channel_id': snippet.get('channelId', ''),
                            'is_history': True
                        }
                    )
                    
                    if created:
                        logger.info(f"Added history video: {snippet.get('title')}")
                    else:
                        # Mark as history if not already
                        if not video_obj.is_history:
                            video_obj.is_history = True
                            video_obj.save(update_fields=['is_history'])
                            logger.info(f"Marked existing video as history: {snippet.get('title')}")
                    
                except Exception as e:
                    logger.error(f"Error processing history video: {str(e)}")
                    continue
                
            return True
            
        except Exception as e:
            logger.exception(f"Exception while fetching watch history: {str(e)}")
            return False

    def sync_user_playlists(self):
        """Fetch and sync the user's playlists"""
        if not self.ensure_valid_token():
            logger.error("Failed to ensure valid token")
            return False

        try:
            # Get user's playlists
            playlists_url = "https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'mine': 'true',
                'maxResults': 50  # Maximum allowed by the API
            }
            headers = {
                'Authorization': f'Bearer {self.user_token.access_token}'
            }
            
            all_playlists = []
            next_page_token = None
            
            # First page
            response = requests.get(playlists_url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch playlists: {response.text}")
                return False
                
            data = response.json()
            playlists = data.get('items', [])
            all_playlists.extend(playlists)
            next_page_token = data.get('nextPageToken')
            
            # Fetch additional pages if available
            while next_page_token:
                params['pageToken'] = next_page_token
                response = requests.get(playlists_url, params=params, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch playlist page: {response.text}")
                    break
                    
                data = response.json()
                playlists = data.get('items', [])
                all_playlists.extend(playlists)
                next_page_token = data.get('nextPageToken')
            
            # Import playlists to database
            for playlist_data in all_playlists:
                playlist_id = playlist_data.get('id')
                snippet = playlist_data.get('snippet', {})
                content_details = playlist_data.get('contentDetails', {})
                
                # Make sure to handle system playlists with user-friendly names
                if playlist_id == 'WL':
                    playlist_data['snippet']['title'] = 'Watch Later'
                elif playlist_id == 'LL':
                    playlist_data['snippet']['title'] = 'Liked Videos'
                    
                # Create or update playlist
                playlist, created = Playlist.objects.update_or_create(
                    user=self.user_token.user,
                    playlist_id=playlist_id,
                    defaults={
                        'title': snippet.get('title', 'Untitled Playlist'),
                        'description': snippet.get('description', ''),
                        'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                        'item_count': content_details.get('itemCount', 0),
                        'youtube_channel_id': snippet.get('channelId', '')
                    }
                )
                
                if created:
                    logger.info(f"Added new playlist: {playlist.title}")
                else:
                    logger.info(f"Updated playlist: {playlist.title}")
                    
                # Sync videos from this playlist
                self._sync_playlist_videos(playlist_id, snippet.get('title'))
            
            logger.info(f"Successfully synced {len(all_playlists)} playlists")
            return True
            
        except Exception as e:
            logger.exception(f"Error syncing playlists: {str(e)}")
            return False

    def _sync_watch_later_videos(self):
        """Sync videos from the Watch Later playlist and update saved status"""
        logger.info("Syncing Watch Later videos")
        
        try:
            # Get all videos currently marked as saved
            existing_saved_videos = Video.objects.filter(
                user=self.user_token.user,
                is_saved=True
            ).values_list('video_id', flat=True)
            existing_saved_videos = set(existing_saved_videos)
            logger.info(f"Found {len(existing_saved_videos)} existing saved videos in database")
            
            # Track videos that are currently in Watch Later
            current_saved_videos = set()
            
            # Get Watch Later videos
            videos = self.get_watch_later_videos()
            
            if videos is None:
                logger.error("Failed to fetch Watch Later videos")
                return False
                
            if len(videos) == 0:
                logger.warning("No videos found in Watch Later playlist (API limitation or empty playlist)")
            else:
                logger.info(f"Processing {len(videos)} videos from Watch Later playlist")
                
                # Process all Watch Later videos
                for item in videos:
                    try:
                        snippet = item.get('snippet', {})
                        video_id = snippet.get('resourceId', {}).get('videoId')
                        
                        if not video_id:
                            logger.warning(f"No video ID in snippet: {snippet}")
                            continue
                            
                        # Add to current saved videos set
                        current_saved_videos.add(video_id)
                        
                        # Create or update video
                        video, created = Video.objects.update_or_create(
                            user=self.user_token.user,
                            video_id=video_id,
                            defaults={
                                'title': snippet.get('title', 'Untitled Video'),
                                'description': snippet.get('description', ''),
                                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                                'published_at': datetime.datetime.fromisoformat(
                                    snippet.get('publishedAt').replace('Z', '+00:00')
                                ),
                                'youtube_description': snippet.get('description', ''),
                                'channel_title': snippet.get('channelTitle', 'Unknown Channel'),
                                'channel_id': snippet.get('channelId', ''),
                                'is_saved': True,
                                'playlist_id': 'WL',
                                'playlist_name': 'Watch Later'
                            }
                        )
                        
                        if created:
                            logger.info(f"Added new Watch Later video: {snippet.get('title')}")
                        else:
                            if not video.is_saved:
                                logger.info(f"Marked existing video as saved: {snippet.get('title')}")
                    except Exception as e:
                        logger.error(f"Error processing Watch Later video: {str(e)}")
                        continue
            
            # Find videos that have been removed from Watch Later
            removed_videos = existing_saved_videos - current_saved_videos
            if removed_videos:
                logger.info(f"Found {len(removed_videos)} videos that are no longer in Watch Later")
                # Update videos that are no longer in Watch Later
                Video.objects.filter(
                    user=self.user_token.user,
                    video_id__in=removed_videos
                ).update(is_saved=False)
            
            # Success even if playlist was empty (API limitation)
            return True
            
        except Exception as e:
            logger.exception(f"Exception while syncing Watch Later videos: {str(e)}")
            return False 