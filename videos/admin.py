from django.contrib import admin
from .models import UserToken, Video, Tag, VideoTag

@admin.register(UserToken)
class UserTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'created_at', 'updated_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'video_id', 'published_at', 'created_at')
    search_fields = ('title', 'video_id', 'user__username')
    list_filter = ('created_at', 'published_at')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    search_fields = ('name', 'user__username')
    list_filter = ('created_at',)

@admin.register(VideoTag)
class VideoTagAdmin(admin.ModelAdmin):
    list_display = ('video', 'tag', 'created_at')
    search_fields = ('video__title', 'tag__name', 'video__user__username')
    list_filter = ('created_at',)
