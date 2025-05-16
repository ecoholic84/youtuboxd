from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Video, Tag, VideoTag, UserToken


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')
        read_only_fields = ('id', 'username', 'email')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']
        read_only_fields = ['id']


class VideoTagSerializer(serializers.ModelSerializer):
    tag = TagSerializer(read_only=True)

    class Meta:
        model = VideoTag
        fields = ('id', 'tag')


class VideoSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        write_only=True,
        required=False
    )

    class Meta:
        model = Video
        fields = ['id', 'youtube_id', 'title', 'description', 'thumbnail_url', 
                 'playlist_id', 'playlist_name', 'tags', 'tag_ids', 'created_at', 'updated_at']
        read_only_fields = ['id', 'youtube_id', 'thumbnail_url', 'playlist_id', 
                           'playlist_name', 'created_at', 'updated_at']

    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', [])
        video = Video.objects.create(**validated_data)
        if tag_ids:
            video.tags.set(tag_ids)
        return video

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if tag_ids is not None:
            instance.tags.set(tag_ids)
        return instance


class VideoDetailSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = (
            'id', 'video_id', 'title', 'description', 'thumbnail_url',
            'published_at', 'youtube_description', 'channel_title',
            'channel_id', 'custom_description', 'tags'
        )

    def get_tags(self, obj):
        video_tags = VideoTag.objects.filter(video=obj)
        return VideoTagSerializer(video_tags, many=True).data


class VideoListSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = (
            'id', 'video_id', 'title', 'thumbnail_url',
            'published_at', 'channel_title', 'custom_description', 'tags'
        )

    def get_tags(self, obj):
        video_tags = VideoTag.objects.filter(video=obj)
        return VideoTagSerializer(video_tags, many=True).data


class VideoUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ('custom_description',)


class TagCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('name',)

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class VideoTagCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoTag
        fields = ('video', 'tag')

    def validate(self, data):
        # Ensure the video belongs to the current user
        if data['video'].user != self.context['request'].user:
            raise serializers.ValidationError("You don't have permission to tag this video.")
        # Ensure the tag belongs to the current user
        if data['tag'].user != self.context['request'].user:
            raise serializers.ValidationError("You don't have permission to use this tag.")
        return data 