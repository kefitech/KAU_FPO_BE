"""
GIS Signals — P2-05
Auto-detects and stores an FPO's agro-climatic zone whenever it's saved,
using FPO.latitude/FPO.longitude (existing fields) to build a Point on
the fly. Zone is stored in FPOZoneAssignment, NOT on FPO itself — see
apps/database/models/gis.py docstring for why (avoids needing to modify
the FPO model, which isn't owned by this module).
"""
from django.contrib.gis.geos import Point
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.database.models import FPO, AgroClimaticZone, FPOZoneAssignment


@receiver(post_save, sender=FPO)
def detect_fpo_agro_zone(sender, instance, **kwargs):
    """
    Runs after every FPO save. Builds a Point from FPO.latitude/longitude
    (both already exist as plain DecimalFields on FPO), finds which
    AgroClimaticZone contains that point, and upserts an
    FPOZoneAssignment row for this FPO.

    NOTE: writes to FPOZoneAssignment — a DIFFERENT model than FPO — so
    this does NOT re-trigger FPO's own post_save signal. No infinite
    recursion risk here, unlike the earlier design that tried to write
    back onto FPO directly (which needed the .update() workaround).
    """
    if instance.latitude is None or instance.longitude is None:
        return

    point = Point(float(instance.longitude), float(instance.latitude), srid=4326)

    zone = AgroClimaticZone.objects.filter(boundary__contains=point).first()

    # Upsert even if zone is None — records that detection was attempted
    # (via detected_at) even when the point falls outside every seeded zone.
    FPOZoneAssignment.objects.update_or_create(
        fpo=instance,
        defaults={'agro_zone': zone},
    )