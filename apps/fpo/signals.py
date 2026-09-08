"""
FPO app signals — Django signal receivers registered at app-ready time.

Currently wires:
    - post_save on every DPRSection<X> model → mark_upstream_chapters_stale
      (per KAU RCD B.5 — AI narrative chapters that depend on this section
      get an amber "may be stale" banner in the FE)

Registration happens via `apps.fpo.apps.FpoConfig.ready()` which imports
this module. Do NOT import models at module load — defer to inside the
receiver bodies so Django's app registry is populated first.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver


# Mapping of each DPRSection<X> model class to its DPR section key.
# Kept as a lazy function so the model imports don't run at module load —
# they run when `register_signals()` is called from apps.py `ready()`, at
# which point Django's app registry is fully initialised.
def _get_section_model_map() -> dict[type, str]:
    from apps.database.models import (
        DPRSectionBaseline,
        DPRSectionCapacity,
        DPRSectionCivil,
        DPRSectionCompliance,
        DPRSectionComponents,
        DPRSectionESS,
        DPRSectionFinance,
        DPRSectionHR,
        DPRSectionImplementation,
        DPRSectionInvestment,
        DPRSectionLocation,
        DPRSectionMachinery,
        DPRSectionMarket,
        DPRSectionNatureOfBusiness,
        DPRSectionProducts,
        DPRSectionRationale,
        DPRSectionRawMaterial,
        DPRSectionRisk,
        DPRSectionSite,
        DPRSectionTechnology,
        DPRSectionUtilities,
    )
    return {
        DPRSectionBaseline:         'baseline',
        DPRSectionCapacity:         'capacity',
        DPRSectionCivil:            'civil',
        DPRSectionCompliance:       'compliance',
        DPRSectionComponents:       'components',
        DPRSectionESS:              'ess',
        DPRSectionFinance:          'finance',
        DPRSectionHR:               'hr',
        DPRSectionImplementation:   'implementation',
        DPRSectionInvestment:       'investment',
        DPRSectionLocation:         'location',
        DPRSectionMachinery:        'machinery',
        DPRSectionMarket:           'market',
        DPRSectionNatureOfBusiness: 'nature-of-business',
        DPRSectionProducts:         'products',
        DPRSectionRationale:        'rationale',
        DPRSectionRawMaterial:      'raw-material',
        DPRSectionRisk:             'risk',
        DPRSectionSite:             'site',
        DPRSectionTechnology:       'technology',
        DPRSectionUtilities:        'utilities',
    }


def _mark_stale_receiver(section_key: str):
    """Return a post_save receiver that marks upstream chapters stale.

    Factory pattern — each model gets its own closure with the section_key
    baked in, so the receiver signature stays clean (Django's post_save
    doesn't accept extra kwargs).
    """
    def _handler(sender, instance, created, **kwargs):
        # Skip stale marking on initial row creation — a brand-new section
        # row with default values shouldn't invalidate chapters that were
        # generated against known populated data. Only actual updates count.
        if created:
            return
        # Import here (not module-top) to avoid app-registry timing issues.
        from apps.fpo.services.dpr.staleness import mark_upstream_chapters_stale
        project = getattr(instance, 'project', None)
        if project is None:
            return
        mark_upstream_chapters_stale(project, section_key)
    return _handler


def register_signals() -> None:
    """Wire the post_save receivers. Called from FpoConfig.ready()."""
    for model_cls, section_key in _get_section_model_map().items():
        # `receiver()` is normally a decorator; call it directly here so we
        # can register one receiver per model in a loop. `weak=False` so
        # the handler isn't garbage-collected while the app is running.
        post_save.connect(
            _mark_stale_receiver(section_key),
            sender=model_cls,
            weak=False,
            dispatch_uid=f'dpr_ai_stale_{section_key}',
        )
