"""Serializers for the session endpoint.

`encrypted_github_token` and `token_scopes` are absent from `fields` by
construction, not by exclusion: the browser has no use for either, and an
explicit allowlist can't leak a column somebody adds later.
"""

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="user_id", read_only=True)
    username = serializers.CharField(source="github_username", read_only=True)
    name = serializers.CharField(source="display_name", read_only=True)
    avatarUrl = serializers.CharField(source="avatar_url", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "name", "email", "avatarUrl"]
        read_only_fields = fields
