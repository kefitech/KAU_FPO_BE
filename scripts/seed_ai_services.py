"""
Seed AIServiceConfig with one row per AI feature.
Author: Athul Gopan (Kefi Tech Solutions)
Created: 21-08-2026

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_ai_services.py').read())
    seed_ai_services()
    "

All 4 services seeded as enabled with no monthly cap.
Admin sets caps after go-live based on actual usage at /api/admin/ai-services/.
"""


def seed_ai_services():
    from apps.database.models import AIServiceConfig

    SERVICES = [
        {
            'service':          AIServiceConfig.Service.DPR_NARRATIVES,
            'is_enabled':       True,
            'monthly_cap_inr':  0,
            'alert_at_pct':     80,
        },
        {
            'service':          AIServiceConfig.Service.CHATBOT,
            'is_enabled':       True,
            'monthly_cap_inr':  0,
            'alert_at_pct':     80,
        },
        {
            'service':          AIServiceConfig.Service.MARKETING,
            'is_enabled':       True,
            'monthly_cap_inr':  0,
            'alert_at_pct':     80,
        },
        {
            'service':          AIServiceConfig.Service.TRANSLATE,
            'is_enabled':       True,
            'monthly_cap_inr':  0,
            'alert_at_pct':     80,
        },
    ]

    created_count = 0
    for item in SERVICES:
        service = item.pop('service')
        _, created = AIServiceConfig.objects.update_or_create(
            service=service,
            defaults=item,
        )
        if created:
            created_count += 1

    print(f'AI services seeded: {created_count} created, {len(SERVICES) - created_count} already existed')
    print('Admin can configure at /api/admin/ai-services/')
