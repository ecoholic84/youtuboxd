from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# DRF router for API endpoints
router = DefaultRouter()
router.register(r'videos', views.VideoViewSet, basename='video')
router.register(r'tags', views.TagViewSet, basename='tag')

# URL patterns
urlpatterns = [
    # Web views
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('video/<int:video_id>/', views.video_detail_view, name='video_detail'),
    
    # Category views
    path('category/<str:category>/', views.video_category_view, name='video_category'),
    path('tag/<int:tag_id>/videos/', views.tag_videos_view, name='tag_videos'),
    path('playlist/<str:playlist_id>/', views.playlist_videos_view, name='playlist_videos'),
    
    # API endpoints
    path('api/', include(router.urls)),
    path('api/videos/<int:video_id>/description/', views.update_video_description, name='update_video_description'),
    path('api/videos/add-tag/', views.add_tag_to_video, name='add_tag_to_video'),
    path('api/videos/remove-tag/', views.remove_tag_from_video, name='remove_tag_from_video'),
    path('api/sync-videos/', views.sync_videos, name='sync_videos'),
    path('api/save-to-drive/', views.save_to_drive, name='save_to_drive'),
    path('api/load-from-drive/', views.load_from_drive, name='load_from_drive'),
] 