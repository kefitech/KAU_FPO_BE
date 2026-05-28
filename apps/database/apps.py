from django.apps import AppConfig


class DatabaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.database"
    verbose_name = "Database Models"

    def ready(self):
        # Import signals when app is ready
        from apps.database.signals import handlers  # noqa: F401
