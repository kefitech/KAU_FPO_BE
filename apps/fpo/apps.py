from django.apps import AppConfig


class FpoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fpo"
    verbose_name = "FPO Management"

    def ready(self):
        # Wire the AI-content staleness post_save receivers so section edits
        # automatically mark the AI narrative chapters that depend on them.
        # Import here (not module-top) so Django's app registry is fully
        # populated before we touch model classes.
        from . import signals as fpo_signals
        fpo_signals.register_signals()
