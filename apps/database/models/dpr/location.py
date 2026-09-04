"""
DPR §2.3.6 — Proposed Project Location.

Single-table section with 6 sub-categories (A-F):
    A. Administrative details (state/district/taluk/local body/village/ward/survey)
    B. Location details (address, PIN, GPS coords, Google Map URL)
    C. Land Ownership Status (M2M → DPRLandOwnershipType, existing master)
    D. Site Status (M2M → DPRSiteStatus, existing master)
    E. Accessibility (6 distance-km numeric fields)
    F. Connectivity (road quality dropdown + 4 internet booleans)
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


LOCAL_BODY_CHOICES = [
    ('grama_panchayat', 'Grama Panchayat'),
    ('municipality',    'Municipality'),
    ('corporation',     'Corporation'),
]

ROAD_CONNECTIVITY_CHOICES = [
    ('excellent', 'Excellent'),
    ('good',      'Good'),
    ('fair',      'Fair'),
    ('poor',      'Poor'),
]


class DPRSectionLocation(TimeStampedModel, AuditModel):
    """§2.3.6 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_location',
    )

    # ── A. Administrative Details ──
    state = models.CharField(max_length=100, blank=True, default='Kerala')
    district = models.CharField(max_length=100, blank=True)
    taluk = models.CharField(max_length=100, blank=True)
    block_panchayat = models.CharField(max_length=100, blank=True)
    local_body_type = models.CharField(max_length=20, choices=LOCAL_BODY_CHOICES, blank=True)
    local_body_name = models.CharField(max_length=200, blank=True)
    village = models.CharField(max_length=100, blank=True)
    ward_number = models.CharField(max_length=50, blank=True)
    survey_number = models.CharField(max_length=100, blank=True)

    # ── B. Location Details ──
    project_address = models.TextField(blank=True)
    landmark = models.CharField(max_length=200, blank=True)
    pin_code = models.CharField(max_length=10, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    google_map_url = models.URLField(blank=True)

    # ── C. Land Ownership Status (multi-select) ──
    land_ownership_types = models.ManyToManyField(
        'database.DPRLandOwnershipType',
        blank=True,
        related_name='+',
    )
    land_ownership_other = models.CharField(max_length=200, blank=True)

    # ── D. Site Status (multi-select) ──
    site_statuses = models.ManyToManyField(
        'database.DPRSiteStatus',
        blank=True,
        related_name='+',
    )
    site_status_other = models.CharField(max_length=200, blank=True)

    # ── E. Accessibility (distances in km) ──
    dist_nearest_main_road_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_nearest_market_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_nearest_collection_centre_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_railway_station_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_airport_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dist_seaport_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # ── F. Connectivity ──
    road_connectivity = models.CharField(max_length=20, choices=ROAD_CONNECTIVITY_CHOICES, blank=True)
    has_fibre = models.BooleanField(default=False)
    has_broadband = models.BooleanField(default=False)
    has_mobile_network = models.BooleanField(default=False)
    internet_unavailable = models.BooleanField(default=False)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_location'
        verbose_name = 'DPR — Location Section'
        verbose_name_plural = 'DPR — Location Sections'

    def __str__(self):
        return f'Location section for project {self.project_id}'
