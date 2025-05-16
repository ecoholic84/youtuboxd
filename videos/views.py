from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.http import JsonResponse, HttpResponseRedirect
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.urls import reverse
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import datetime
import logging
import requests
from django.db import models

from .models import UserToken, Video, Tag, VideoTag, Playlist
from .serializers import (
    VideoListSerializer, VideoDetailSerializer, VideoUpdateSerializer,
    TagSerializer, TagCreateSerializer, VideoTagCreateSerializer
)
from .youtube_api import YouTubeAPI
from .drive_service import GoogleDriveService

logger = logging.getLogger(__name__)

# Web Views
def login_view(request):
    """Render the login page with Google OAuth link"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    auth_url = YouTubeAPI.get_auth_url()
    return render(request, 'videos/login.html', {'auth_url': auth_url})

@login_required
def dashboard_view(request):
    """Render the dashboard with user's videos in different categories"""
    # Check for drive operations
    if 'load_from_drive' in request.GET:
        drive_service = GoogleDriveService(user=request.user)
        success = drive_service.load_tags_from_drive()
        if success:
            return redirect('dashboard')
        else:
            # Continue with dashboard view even if loading failed
            pass
            
    # Sync videos if requested
    if 'sync' in request.GET:
        youtube_api = YouTubeAPI(user=request.user)
        youtube_api.sync_videos_for_user()
        return redirect('dashboard')
        
    # Get user tags for sidebar
    user_tags = Tag.objects.filter(user=request.user).order_by('name')
    
    # Get user playlists for sidebar
    user_playlists = Playlist.objects.filter(user=request.user).order_by('title')
    
    # Initialize YouTube API
    youtube_api = YouTubeAPI(user=request.user)
    
    # Get video categories
    video_categories = {}
    

    
    # Get liked videos (only if we don't have a playlist for them)
    has_liked_playlist = Playlist.objects.filter(user=request.user, playlist_id='LL').exists()
    if not has_liked_playlist:
        liked_videos = Video.objects.filter(user=request.user, is_liked=True).order_by('-published_at')[:12]
        if liked_videos.exists():
            video_categories['Liked Videos'] = {
                'videos': liked_videos,
                'view_all_url': reverse('video_category', kwargs={'category': 'liked'}),
                'empty_message': 'No liked videos found',
                'icon': 'fa-heart'
            }
    
    # Get saved videos (only if we don't have a playlist for them)
    has_saved_playlist = Playlist.objects.filter(user=request.user, playlist_id='WL').exists()
    if not has_saved_playlist:
        # Get saved videos - all videos in playlists or marked as saved, except liked videos
        saved_videos = Video.objects.filter(
            user=request.user
        ).filter(
            models.Q(is_saved=True) | ~models.Q(playlist_id='')
        ).exclude(
            is_liked=True
        ).order_by('-published_at')[:12]
        
        if saved_videos.exists():
            video_categories['Saved Videos'] = {
                'videos': saved_videos,
                'view_all_url': reverse('video_category', kwargs={'category': 'saved'}),
                'empty_message': 'No saved videos found',
                'icon': 'fa-bookmark'
            }
    
    # Get videos by tag (one row per tag, limited to top 3 tags with most videos)
    tags_with_counts = Tag.objects.filter(user=request.user).annotate(
        video_count=models.Count('tagged_videos')
    ).order_by('-video_count')[:3]
    
    for tag in tags_with_counts:
        tag_videos = Video.objects.filter(
            user=request.user, 
            video_tags__tag=tag
        ).order_by('-published_at')[:12]
        
        if tag_videos.exists():
            video_categories[f'Tagged: {tag.name}'] = {
                'videos': tag_videos,
                'view_all_url': reverse('tag_videos', kwargs={'tag_id': tag.id}),
                'empty_message': f'No videos tagged with {tag.name}',
                'icon': 'fa-tag'
            }
    
    # Get videos from user playlists
    for playlist in user_playlists:
        # Skip Liked Videos and Watch Later if we're already showing them
        if (playlist.playlist_id == 'LL' and 'Liked Videos' in video_categories) or \
           (playlist.playlist_id == 'WL' and 'Saved Videos' in video_categories):
            continue
            
        playlist_videos = Video.objects.filter(
            user=request.user,
            playlist_id=playlist.playlist_id
        ).order_by('-published_at')[:12]
        
        if playlist_videos.exists():
            video_categories[f'Playlist: {playlist.title}'] = {
                'videos': playlist_videos,
                'view_all_url': reverse('playlist_videos', kwargs={'playlist_id': playlist.playlist_id}) 
                if playlist.playlist_id not in ['LL', 'WL'] else 
                reverse('video_category', kwargs={'category': 'liked' if playlist.playlist_id == 'LL' else 'saved'}),
                'empty_message': f'No videos in playlist {playlist.title}',
                'icon': 'fa-heart' if playlist.playlist_id == 'LL' else 'fa-bookmark' if playlist.playlist_id == 'WL' else 'fa-list'
            }
    
    return render(request, 'videos/dashboard.html', {
        'video_categories': video_categories,
        'user_tags': user_tags,
        'user_playlists': user_playlists,
    })

@login_required
def video_detail_view(request, video_id):
    """Render the detail page for a specific video"""
    video = get_object_or_404(Video, user=request.user, id=video_id)
    
    # Get all user tags and video tags
    user_tags = Tag.objects.filter(user=request.user).order_by('name')
    video_tags = VideoTag.objects.filter(video=video).values_list('tag_id', flat=True)
    
    # Get user playlists for sidebar
    user_playlists = Playlist.objects.filter(user=request.user).order_by('title')
    
    return render(request, 'videos/video_detail.html', {
        'video': video,
        'user_tags': user_tags,
        'tags': user_tags,  # For backward compatibility
        'user_playlists': user_playlists,
        'video_tags': list(video_tags),
    })

def oauth_callback(request):
    """Handle the OAuth callback from Google"""
    error = request.GET.get('error')
    if error:
        return render(request, 'videos/login.html', {'error': error})
        
    code = request.GET.get('code')
    if not code:
        return redirect('login')
    
    youtube_api = YouTubeAPI()
    token_data = youtube_api.exchange_code_for_tokens(code)
    
    if not token_data:
        return render(request, 'videos/login.html', {'error': 'Failed to get tokens'})
    
    # Get user info from Google
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 3600)  # Default to 1 hour
    
    if not access_token:
        return render(request, 'videos/login.html', {'error': 'No access token received'})
    
    # Get user profile with the access token
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        # Try the Google OAuth2 userinfo endpoint
        response = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to get user info from Google OAuth2: {response.status_code}, {response.text}")
            # Try another Google endpoint as fallback
            response = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to get user info from fallback endpoint: {response.status_code}, {response.text}")
                return render(request, 'videos/login.html', {'error': f'Failed to get user info: {response.status_code}. Make sure you allowed the required permissions.'})
        
        user_data = response.json()
        logger.info(f"Retrieved user data: {user_data}")
        
        email = user_data.get('email')
        
        if not email:
            # If no email, try to use the user's ID as an identifier
            if 'id' in user_data:
                email = f"{user_data.get('id')}@youtuboxd.user"
            else:
                return render(request, 'videos/login.html', {'error': 'No email or ID received from Google'})
        
    except Exception as e:
        logger.exception("Exception during user info retrieval")
        return render(request, 'videos/login.html', {'error': f'Error getting user info: {str(e)}'})
    
    # Find or create the user
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Create a new user
        username = email.split('@')[0]
        # Make sure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
            
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=user_data.get('given_name', ''),
            last_name=user_data.get('family_name', '')
        )
    
    # Store or update the tokens
    expires_at = timezone.now() + datetime.timedelta(seconds=expires_in)
    
    UserToken.objects.update_or_create(
        user=user,
        defaults={
            'access_token': access_token,
            'refresh_token': refresh_token or '',  # Sometimes refresh token isn't returned on re-auth
            'expires_at': expires_at
        }
    )
    
    # Log the user in
    login(request, user)
    
    # Sync videos for the user
    youtube_api = YouTubeAPI(user=user)
    youtube_api.sync_videos_for_user()
    
    return redirect('dashboard')

# API Views
class VideoViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for listing and retrieving videos"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Video.objects.filter(user=self.request.user).order_by('-published_at')
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VideoDetailSerializer
        return VideoListSerializer

class TagViewSet(viewsets.ModelViewSet):
    """API viewset for managing tags"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user).order_by('name')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update']:
            return TagCreateSerializer
        return TagSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_tag_to_video(request):
    """Add a tag to a video"""
    video_id = request.data.get('video_id')
    tag_id = request.data.get('tag_id')
    
    if not video_id or not tag_id:
        return Response(
            {'error': 'Video ID and Tag ID are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        video = Video.objects.get(id=video_id, user=request.user)
        tag = Tag.objects.get(id=tag_id, user=request.user)
    except (Video.DoesNotExist, Tag.DoesNotExist):
        return Response(
            {'error': 'Invalid Video ID or Tag ID'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Create the relation if it doesn't exist
    video_tag, created = VideoTag.objects.get_or_create(video=video, tag=tag)
    
    return Response(
        {'success': True, 'created': created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_tag_from_video(request):
    """Remove a tag from a video"""
    video_id = request.data.get('video_id')
    tag_id = request.data.get('tag_id')
    
    if not video_id or not tag_id:
        return Response(
            {'error': 'Video ID and Tag ID are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        VideoTag.objects.filter(
            video__id=video_id,
            tag__id=tag_id,
            video__user=request.user
        ).delete()
        return Response({'success': True}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_video_description(request, video_id):
    """Update a video's custom description"""
    try:
        video = Video.objects.get(id=video_id, user=request.user)
    except Video.DoesNotExist:
        return Response(
            {'error': 'Video not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = VideoUpdateSerializer(video, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_videos(request):
    """Manually trigger a sync of the user's YouTube videos"""
    sync_type = request.data.get('sync_type', 'all')
    youtube_api = YouTubeAPI(user=request.user)
    
    if sync_type == 'liked':
        # Only sync liked videos
        success = youtube_api._sync_liked_videos()
        message = "Liked videos synced successfully"
    elif sync_type == 'saved':
        # Only sync watch later videos
        success = youtube_api._sync_watch_later_videos()
        message = "Saved videos synced successfully"
    else:
        # Sync all videos
        success = youtube_api.sync_videos_for_user()
        message = "All videos synced successfully"
    
    if success:
        return Response({'success': True, 'message': message})
    else:
        return Response(
            {'success': False, 'message': 'Failed to sync videos'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@login_required
def video_category_view(request, category):
    """View for a specific category of videos"""
    # Get all user tags
    user_tags = Tag.objects.filter(user=request.user).order_by('name')
    
    # Get user playlists for sidebar
    user_playlists = Playlist.objects.filter(user=request.user).order_by('title')
    
    # Get videos based on category
    if category == 'liked':
        videos = Video.objects.filter(user=request.user, is_liked=True).order_by('-published_at')
        title = "Liked Videos"
        icon = "fa-heart"
    elif category == 'history':
        # Redirect to dashboard if history category is accessed directly
        return redirect('dashboard')
    elif category == 'recent':
        # Redirect to dashboard if recent category is accessed directly
        return redirect('dashboard')
    elif category == 'saved':
        # For saved videos, show videos in playlists or marked as saved, but exclude liked videos
        videos = Video.objects.filter(
            user=request.user
        ).filter(
            models.Q(is_saved=True) | ~models.Q(playlist_id='')
        ).exclude(
            is_liked=True
        ).order_by('-published_at')
        title = "Saved Videos"
        icon = "fa-bookmark"
    else:
        # Default to all videos
        videos = Video.objects.filter(user=request.user).order_by('-published_at')
        title = "All Videos"
        icon = "fa-video"
    
    return render(request, 'videos/category.html', {
        'videos': videos,
        'user_tags': user_tags,
        'tags': user_tags,  # For backward compatibility
        'user_playlists': user_playlists,
        'title': title,
        'icon': icon,
        'category': category
    })

@login_required
def tag_videos_view(request, tag_id):
    """View for videos with a specific tag"""
    # Get the tag
    tag = get_object_or_404(Tag, id=tag_id, user=request.user)
    
    # Get all user tags
    user_tags = Tag.objects.filter(user=request.user).order_by('name')
    
    # Get user playlists for sidebar
    user_playlists = Playlist.objects.filter(user=request.user).order_by('title')
    
    # Get videos with this tag
    videos = Video.objects.filter(
        user=request.user,
        video_tags__tag=tag
    ).order_by('-published_at')
    
    return render(request, 'videos/category.html', {
        'videos': videos,
        'user_tags': user_tags,
        'tags': user_tags,  # For backward compatibility
        'user_playlists': user_playlists,
        'title': f"Videos Tagged: {tag.name}",
        'icon': "fa-tag",
        'category': f"tag-{tag.id}"
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_to_drive(request):
    """Save user's tags to Google Drive"""
    drive_service = GoogleDriveService(user=request.user)
    success = drive_service.save_tags_to_drive()
    
    if success:
        return Response({
            'success': True,
            'message': 'Successfully saved tags to Google Drive'
        })
    else:
        return Response({
            'success': False,
            'message': 'Failed to save tags to Google Drive'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def load_from_drive(request):
    """Load user's tags from Google Drive"""
    drive_service = GoogleDriveService(user=request.user)
    success = drive_service.load_tags_from_drive()
    
    if success:
        return Response({
            'success': True,
            'message': 'Successfully loaded tags from Google Drive'
        })
    else:
        return Response({
            'success': False,
            'message': 'Failed to load tags from Google Drive'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def logout_view(request):
    """
    Custom logout view that properly handles OAuth sessions
    - Clears Django session
    - Clears session cookies
    - Maintains OAuth connection (doesn't revoke tokens)
    - Redirects to login page
    """
    from django.contrib.auth import logout
    from django.contrib.sessions.models import Session
    
    try:
        # Get the user before logout
        user = request.user
        
        # Perform Django logout (clears session)
        logout(request)
        
        # If the user was authenticated, clear their session data
        if user.is_authenticated:
            # Clear any specific session data
            if hasattr(request, 'session'):
                request.session.flush()
            
            # Clear any cookies related to the session
            response = redirect('login')
            response.delete_cookie('sessionid')
            response.delete_cookie('csrftoken')
            
            # Log the logout
            logger.info(f"User {user.username} successfully logged out")
            
            return response
            
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
    
    # Default redirect if any issues
    return redirect('login')

@login_required
def playlist_videos_view(request, playlist_id):
    """View for videos in a specific playlist"""
    # Get all user tags
    user_tags = Tag.objects.filter(user=request.user).order_by('name')
    
    # Get all user playlists
    user_playlists = Playlist.objects.filter(user=request.user).order_by('title')
    
    # Handle special playlists
    if playlist_id == 'LL':
        return redirect('video_category', category='liked')
    elif playlist_id == 'WL':
        return redirect('video_category', category='saved')
    
    # Get the playlist
    try:
        playlist = Playlist.objects.get(user=request.user, playlist_id=playlist_id)
        title = f"Playlist: {playlist.title}"
    except Playlist.DoesNotExist:
        # If playlist doesn't exist in our database but is a valid YouTube playlist
        title = f"Playlist: {playlist_id}"
    
    # Get videos from this playlist
    videos = Video.objects.filter(
        user=request.user,
        playlist_id=playlist_id
    ).order_by('-published_at')
    
    return render(request, 'videos/category.html', {
        'videos': videos,
        'user_tags': user_tags,
        'user_playlists': user_playlists,
        'title': title,
        'icon': "fa-list",
        'category': f"playlist-{playlist_id}"
    })
