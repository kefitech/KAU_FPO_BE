from django.apps import AppConfig


class ExternalBuyerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.external_buyer'
    verbose_name = 'External Buyer'