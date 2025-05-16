import json
import logging
import requests
from django.conf import settings
from django.utils import timezone
import datetime
from .models import UserToken, Tag, VideoTag, Video

logger = logging.getLogger(__name__)

class GoogleDriveService:
    """Service to interact with Google Drive API"""
    
    DRIVE_API_BASE_URL = "https://www.googleapis.com/drive/v3"
    UPLOAD_API_URL = "https://www.googleapis.com/upload/drive/v3/files"
    APP_FOLDER_NAME = "YouTuBoxd Data"
    TAGS_FILE_NAME = "youtuboxd_tags.json"
    
    def __init__(self, user):
        """Initialize with user"""
        self.user = user
        try:
            self.user_token = UserToken.objects.get(user=user)
        except UserToken.DoesNotExist:
            self.user_token = None

    def ensure_valid_token(self):
        """Ensure the access token is valid, refreshing if needed"""
        if not self.user_token:
            logger.error("No user token available")
            return False
            
        # Check if token is expired or will expire in the next 5 minutes
        if self.user_token.expires_at <= timezone.now() + datetime.timedelta(minutes=5):
            return self._refresh_access_token()
            
        return True
    
    def _refresh_access_token(self):
        """Refresh the access token using the refresh token"""
        if not self.user_token or not self.user_token.refresh_token:
            logger.error("No refresh token available")
            return False
            
        payload = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'refresh_token': self.user_token.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post("https://oauth2.googleapis.com/token", data=payload)
        
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
    
    def _get_app_folder(self):
        """Get or create the app folder in Drive"""
        if not self.ensure_valid_token():
            return None
            
        # Check if folder already exists
        query = f"name='{self.APP_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        url = f"{self.DRIVE_API_BASE_URL}/files"
        params = {
            "q": query,
            "fields": "files(id, name)"
        }
        headers = {"Authorization": f"Bearer {self.user_token.access_token}"}
        
        response = requests.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to search for app folder: {response.text}")
            return None
            
        files = response.json().get("files", [])
        
        if files:
            # Folder exists, return its ID
            return files[0]["id"]
        else:
            # Create folder
            return self._create_app_folder()
    
    def _create_app_folder(self):
        """Create the app folder in Drive"""
        if not self.ensure_valid_token():
            return None
            
        url = f"{self.DRIVE_API_BASE_URL}/files"
        headers = {
            "Authorization": f"Bearer {self.user_token.access_token}",
            "Content-Type": "application/json"
        }
        data = {
            "name": self.APP_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder"
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            logger.error(f"Failed to create app folder: {response.text}")
            return None
            
        return response.json().get("id")
    
    def _get_tags_file(self, folder_id):
        """Get the tags file if it exists"""
        if not self.ensure_valid_token() or not folder_id:
            return None
            
        query = f"name='{self.TAGS_FILE_NAME}' and '{folder_id}' in parents and trashed=false"
        url = f"{self.DRIVE_API_BASE_URL}/files"
        params = {
            "q": query,
            "fields": "files(id, name)"
        }
        headers = {"Authorization": f"Bearer {self.user_token.access_token}"}
        
        response = requests.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to search for tags file: {response.text}")
            return None
            
        files = response.json().get("files", [])
        
        if files:
            return files[0]["id"]
        else:
            return None
    
    def save_tags_to_drive(self):
        """Save user's tags and video tags to Google Drive"""
        logger.info(f"Saving tags to Drive for user: {self.user.username}")
        
        # Get app folder ID
        folder_id = self._get_app_folder()
        if not folder_id:
            logger.error("Failed to get or create app folder")
            return False
        
        # Collect all user tags and their associated videos
        tags_data = {}
        
        user_tags = Tag.objects.filter(user=self.user)
        for tag in user_tags:
            video_tags = VideoTag.objects.filter(tag=tag)
            videos = []
            
            for video_tag in video_tags:
                video = video_tag.video
                videos.append({
                    "video_id": video.video_id,
                    "title": video.title,
                    "thumbnail_url": video.thumbnail_url,
                    "custom_description": video.custom_description,
                    "added_at": video_tag.created_at.isoformat() if video_tag.created_at else None
                })
            
            tags_data[tag.name] = {
                "id": tag.id,
                "created_at": tag.created_at.isoformat() if tag.created_at else None,
                "videos": videos
            }
        
        # Export data as JSON
        export_data = {
            "user": self.user.username,
            "exported_at": timezone.now().isoformat(),
            "tags": tags_data
        }
        json_data = json.dumps(export_data, indent=2)
        
        # Check if tags file already exists
        file_id = self._get_tags_file(folder_id)
        
        if file_id:
            # Update existing file
            return self._update_tags_file(file_id, json_data)
        else:
            # Create new file
            return self._create_tags_file(folder_id, json_data)
    
    def _create_tags_file(self, folder_id, content):
        """Create a new tags file in Drive"""
        if not self.ensure_valid_token():
            return False
            
        # First create metadata
        url = f"{self.DRIVE_API_BASE_URL}/files"
        headers = {
            "Authorization": f"Bearer {self.user_token.access_token}",
            "Content-Type": "application/json"
        }
        metadata = {
            "name": self.TAGS_FILE_NAME,
            "parents": [folder_id],
            "mimeType": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=metadata)
        
        if response.status_code != 200:
            logger.error(f"Failed to create tags file metadata: {response.text}")
            return False
            
        file_id = response.json().get("id")
        
        # Then upload content
        url = f"{self.DRIVE_API_BASE_URL}/files/{file_id}/content"
        headers = {
            "Authorization": f"Bearer {self.user_token.access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.patch(url, headers=headers, data=content)
        
        if response.status_code not in (200, 204):
            logger.error(f"Failed to upload tags file content: {response.text}")
            return False
            
        logger.info(f"Created tags file in Drive for user: {self.user.username}")
        return True
    
    def _update_tags_file(self, file_id, content):
        """Update an existing tags file in Drive"""
        if not self.ensure_valid_token():
            return False
            
        url = f"{self.UPLOAD_API_URL}/{file_id}?uploadType=media"
        headers = {
            "Authorization": f"Bearer {self.user_token.access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.patch(url, headers=headers, data=content)
        
        if response.status_code not in (200, 204):
            logger.error(f"Failed to update tags file: {response.text}")
            return False
            
        logger.info(f"Updated tags file in Drive for user: {self.user.username}")
        return True
    
    def load_tags_from_drive(self):
        """Load user's tags from Google Drive and restore them"""
        logger.info(f"Loading tags from Drive for user: {self.user.username}")
        
        # Get app folder ID
        folder_id = self._get_app_folder()
        if not folder_id:
            logger.error("Failed to get app folder")
            return False
        
        # Get tags file
        file_id = self._get_tags_file(folder_id)
        if not file_id:
            logger.info("No tags file found in Drive")
            return False
        
        # Download file content
        if not self.ensure_valid_token():
            return False
            
        url = f"{self.DRIVE_API_BASE_URL}/files/{file_id}?alt=media"
        headers = {"Authorization": f"Bearer {self.user_token.access_token}"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to download tags file: {response.text}")
            return False
        
        try:
            # Parse JSON data
            tags_data = response.json()
            
            # Import tags
            imported_count = 0
            for tag_name, tag_info in tags_data.get("tags", {}).items():
                # Create tag if it doesn't exist
                tag, created = Tag.objects.get_or_create(
                    user=self.user,
                    name=tag_name
                )
                
                # Process videos for this tag
                for video_data in tag_info.get("videos", []):
                    video_id = video_data.get("video_id")
                    
                    # Check if we have this video
                    try:
                        video = Video.objects.get(user=self.user, video_id=video_id)
                        
                        # Create video tag relation if it doesn't exist
                        video_tag, created = VideoTag.objects.get_or_create(
                            video=video,
                            tag=tag
                        )
                        
                        # Update custom description if available
                        custom_description = video_data.get("custom_description")
                        if custom_description and not video.custom_description:
                            video.custom_description = custom_description
                            video.save(update_fields=["custom_description"])
                        
                        imported_count += 1
                        
                    except Video.DoesNotExist:
                        # We don't have this video yet, it might be synced later
                        pass
            
            logger.info(f"Imported {imported_count} tag-video relationships from Drive")
            return True
            
        except Exception as e:
            logger.exception(f"Error parsing tags data: {str(e)}")
            return False 