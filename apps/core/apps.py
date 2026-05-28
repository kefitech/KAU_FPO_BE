from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        """
        Import signal handlers and register OpenAPI extensions when Django starts.
        """
        # Import schema extensions to register them with drf-spectacular
        from apps.core import schema  # noqa: F401
