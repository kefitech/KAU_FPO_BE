from django.apps import AppConfig


class GisModuleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gis_module"
    verbose_name = "GIS Module"

    def ready(self):
        import apps.gis_module.signals  # noqa: F401git diff feature/p2-05-gis-zones feature/p2-06-recommendations-api -- apps/gis_module/ apps/database/models/gis.py apps/database/models/__init__.py
