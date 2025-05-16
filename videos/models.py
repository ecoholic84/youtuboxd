from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserToken(models.Model):
    """Store OAuth tokens for users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='token')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_expired(self):
        """Check if the access token has expired"""
        return self.expires_at <= timezone.now()

    def __str__(self):
        return f"Token for {self.user.username}"


class Playlist(models.Model):
    """Store user's YouTube playlists"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playlists')
    playlist_id = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    thumbnail_url = models.URLField(blank=True, null=True)
    item_count = models.IntegerField(default=0)
    youtube_channel_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'playlist_id')
    
    def __str__(self):
        return self.title


class Video(models.Model):
    """Store YouTube video data"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='videos')
    video_id = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    youtube_description = models.TextField(blank=True, null=True)
    custom_description = models.TextField(blank=True, null=True)
    thumbnail_url = models.URLField(blank=True, null=True)
    channel_title = models.CharField(max_length=255, blank=True, null=True)
    channel_id = models.CharField(max_length=100, blank=True, null=True)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Category fields
    is_liked = models.BooleanField(default=False)
    is_history = models.BooleanField(default=False)
    is_saved = models.BooleanField(default=False)  # For Watch Later
    
    # Reference to source playlist if applicable
    playlist_id = models.CharField(max_length=100, blank=True, null=True)
    playlist_name = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        unique_together = ('user', 'video_id')
        ordering = ['-published_at']

    def __str__(self):
        return self.title


class Tag(models.Model):
    """Store tags for videos"""
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'user')

    def __str__(self):
        return self.name


class VideoTag(models.Model):
    """Many-to-many relationship between videos and tags"""
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='video_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='tagged_videos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'tag')

    def __str__(self):
        return f"{self.video.title} - {self.tag.name}"
