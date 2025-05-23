# Generated by Django 5.1.7 on 2025-05-16 03:31

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0003_alter_usertoken_refresh_token_alter_video_channel_id_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WatchEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('watched_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.CharField(default='app', max_length=50)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watch_events', to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watch_events', to='videos.video')),
            ],
            options={
                'ordering': ['-watched_at'],
                'indexes': [models.Index(fields=['user', '-watched_at'], name='videos_watc_user_id_036740_idx'), models.Index(fields=['video', '-watched_at'], name='videos_watc_video_i_b767e8_idx')],
            },
        ),
    ]
