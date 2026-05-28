"""
Notification Serializers
========================

Author: Athul Gopan (Kefi Tech Solutions)
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.database.models import NotificationTemplateCode, NotificationTemplate


class NotificationTemplateCodeSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationTemplateCode (the definition/parent).

    Includes a count of how many language versions exist and which languages
    are still missing — useful for the admin dashboard completion view.
    """

    channel_display   = serializers.CharField(source='get_channel_display', read_only=True)
    template_count    = serializers.SerializerMethodField()
    missing_languages = serializers.SerializerMethodField()
    variables         = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        default=list,
        help_text="Variable names used in the template body e.g. ['user_name', 'fpo_name']"
    )

    class Meta:
        model  = NotificationTemplateCode
        fields = [
            'id',
            'code',
            'name',
            'channel',
            'channel_display',
            'variables',
            'description',
            'is_active',
            'template_count',
            'missing_languages',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'channel_display', 'template_count', 'missing_languages', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_template_count(self, obj):
        # Use prefetched cache — avoid extra DB hit per row
        return sum(1 for t in obj.templates.all() if t.is_active)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_missing_languages(self, obj):
        return list(obj.missing_languages)


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationTemplate (language-specific content).

    On read: expands template_code and language for display.
    On write: accepts template_code (FK id) and language (FK id).
    """

    # Read-only display fields
    template_code_detail = NotificationTemplateCodeSerializer(source='template_code', read_only=True)
    language_code        = serializers.CharField(source='language.code', read_only=True)
    language_name        = serializers.CharField(source='language.native_name', read_only=True)
    channel              = serializers.CharField(source='template_code.channel', read_only=True)
    channel_display      = serializers.CharField(source='template_code.get_channel_display', read_only=True)
    variables            = serializers.ListField(child=serializers.CharField(), source='template_code.variables', read_only=True)

    class Meta:
        model  = NotificationTemplate
        fields = [
            'id',
            'template_code',
            'template_code_detail',
            'language',
            'language_code',
            'language_name',
            'channel',
            'channel_display',
            'variables',
            'subject',
            'body',
            'is_active',
            'whatsapp_template_name',
            'whatsapp_template_language',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'template_code_detail',
            'language_code',
            'language_name',
            'channel',
            'channel_display',
            'variables',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'whatsapp_template_name': {
                'help_text': 'Meta-approved WhatsApp template name. Required for whatsapp channel.'
            },
            'whatsapp_template_language': {
                'help_text': "Language code matching the Meta-approved template (e.g. 'en', 'ml'). Defaults to 'en'."
            },
        }

    def validate(self, data):
        template_code = data.get('template_code', getattr(self.instance, 'template_code', None))
        language      = data.get('language',      getattr(self.instance, 'language',      None))

        # Subject required for email channel
        if template_code and template_code.channel == NotificationTemplateCode.Channel.EMAIL:
            subject = data.get('subject', getattr(self.instance, 'subject', ''))
            if not subject:
                raise serializers.ValidationError({'subject': 'Subject is required for email templates.'})

        # WhatsApp template name required for whatsapp channel
        if template_code and template_code.channel == NotificationTemplateCode.Channel.WHATSAPP:
            wa_name = data.get('whatsapp_template_name', getattr(self.instance, 'whatsapp_template_name', ''))
            if not wa_name:
                raise serializers.ValidationError(
                    {'whatsapp_template_name': 'whatsapp_template_name is required for WhatsApp channel templates.'}
                )

        # Duplicate check (exclude self on update)
        qs = NotificationTemplate.objects.filter(template_code=template_code, language=language)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A template for '{template_code.code}' in '{language.code}' already exists."
            )

        return data
