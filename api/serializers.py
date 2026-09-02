import json

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from api.utils import RawCommand
from .models import (
    SaltReturns,
    SaltEvents,
    Keys,
    Minions,
    MinionsCustomFields,
    Conformity,
    UserSettings,
    Functions,
    Schedule,
    JobTemplate,
    AuditLog,
)


class SaltReturnsSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    arguments = serializers.CharField()
    keyword_arguments = serializers.CharField()
    # None where the record does not say; the UI shows that as unknown rather
    # than inventing a verdict in either direction.
    success = serializers.BooleanField(source="success_bool", allow_null=True)

    class Meta:
        model = SaltReturns
        # `return` and `full_ret` are the job payload, which for a highstate
        # runs to hundreds of kilobytes. No consumer renders them - the detail
        # view fetches formatted output from /rendered_state/ - so they are not
        # worth putting on the wire once per row. full_ret is still loaded,
        # because arguments, keyword_arguments and success are derived from it.
        exclude = ("return_field", "full_ret")

    def get_user(self, obj):
        # SaltReturns.user() reads the jids table one row at a time. The list
        # views put every jid's user in the context up front so a page of
        # results costs one query instead of one per row.
        users = self.context.get("jid_users")
        if users is not None:
            return users.get(obj.jid, "")
        return obj.user()


class EventsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaltEvents
        fields = "__all__"


class KeysSerializer(serializers.ModelSerializer):
    class Meta:
        model = Keys
        fields = "__all__"


class MinionsCustomFieldsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MinionsCustomFields
        fields = ("name", "function", "value")


class FunctionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Functions
        fields = "__all__"


class MinionsSerializer(serializers.ModelSerializer):
    last_job = serializers.DateTimeField(source="last_job.alter_time", default=None)
    last_highstate = serializers.DateTimeField(
        source="last_highstate_time", default=None
    )
    conformity = serializers.BooleanField()
    custom_fields = MinionsCustomFieldsSerializer(many=True, read_only=True)

    class Meta:
        model = Minions
        fields = "__all__"

    def to_representation(self, instance):
        data = super(MinionsSerializer, self).to_representation(instance)
        data["conformity"] = (
            "Unknown" if data["conformity"] is None else str(data["conformity"])
        )
        return data


class ConformitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Conformity
        fields = "__all__"


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = "__all__"
        # `token` is the password this user authenticates to Salt with, so only
        # the token endpoints may change it. A settings PATCH carries the
        # preferences blob and nothing else.
        read_only_fields = ("user", "token", "created", "salt_permissions")


class JobTemplateSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        name = validated_data["name"]
        job = validated_data["job"]
        command = RawCommand(job)
        parsed_command = command.parse()
        obj, created = JobTemplate.objects.update_or_create(
            name=name, defaults={"job": json.dumps(parsed_command[0])}
        )
        return obj

    class Meta:
        model = JobTemplate
        fields = "__all__"


class UsersSerializer(serializers.ModelSerializer):
    user_settings = UserSettingsSerializer(read_only=True)

    def create(self, validated_data):
        # Remove useless fields. A JSON request omits them entirely, unlike an
        # HTML form post where DRF supplies a value for every declared field,
        # so these have to be discarded without assuming they are present.
        for param in ["is_active", "groups", "user_permissions"]:
            validated_data.pop(param, None)
        password = validated_data.pop("password")
        # Only staff may create another staff user.
        current_user = self.context["request"].user
        if not current_user.is_staff:
            validated_data.pop("is_staff", None)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        # Prevent an unprivileged user to escalate status.
        current_user = self.context["request"].user
        if not current_user.is_staff:
            validated_data.pop("is_staff", None)
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

    def get_extra_kwargs(self):
        # Override password validation on update.
        extra_kwargs = super(UsersSerializer, self).get_extra_kwargs()
        action = self.context["view"].action
        if action in ["update", "partial_update"]:
            extra_kwargs["password"] = {"write_only": True, "required": False}
        return extra_kwargs

    class Meta:
        model = User
        fields = "__all__"
        extra_kwargs = {"password": {"write_only": True}}


class ScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = "__all__"


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)

        # Add extra responses here
        data["username"] = self.user.username
        data["id"] = self.user.id
        data["email"] = self.user.email
        data["is_staff"] = self.user.is_staff
        return data


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ("id", "username", "action", "target", "detail", "created")
