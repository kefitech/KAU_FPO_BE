from django.db import migrations


MISSION_TITLE = {
    "en": "The Mission",
    "ml": "",
}

MISSION_BODY = {
    "en": (
        "<p style=\"text-align: justify;\">The KAU-FPO Linkage (KFL) project will work with a mission "
        "to ignite a sustainable agricultural development in Kerala by empowering FPOs as the driving "
        "force. This will be achieved through a transformative partnership between Kerala Agricultural "
        "University (KAU) and FPOs, synergizing academic brilliance with practical experience. The core "
        "mission encompasses the following:</p>"
        "<ul class=\"check-solid-list mt-20\">"
        "<li style=\"text-align: justify;\">Empowerment of FPOs for excellence: Empowering FPO members "
        "through knowledge and entrepreneurial skill development, equipping them to conquer the "
        "challenges of modern agriculture and propel their organizations towards self-sufficiency</li>"
        "<li style=\"text-align: justify;\">Research for impact: Fueling groundbreaking business and "
        "policy-oriented research directly addressing the critical issues faced by FPOs. This research "
        "will be a cornerstone for providing actionable solutions for their growth and propelling "
        "informed decision-making</li>"
        "<li style=\"text-align: justify;\">Building sustainable FPO ecosystems: Foster a collaborative "
        "environment and provide handholding support to streamline FPO activities, ensuring their "
        "long-term sustainability and maximising their impact on Kerala's agriculture.</li>"
        "</ul>"
    ),
    "ml": "",
}

VISION_TITLE = {
    "en": "The Vision",
    "ml": "",
}

VISION_BODY = {
    "en": (
        "<p style=\"text-align: justify;\">The KAU-FPO Linkage (KFL) project envisions a future where "
        "FPOs in Kerala flourish as empowered and self-sustaining institutions driven by strategic "
        "collaboration between the academic expertise of Kerala Agricultural University and the "
        "invaluable real-world experience of FPO members.</p>"
    ),
    "ml": "",
}

BLOCKS = [
    ("mission_title", MISSION_TITLE),
    ("mission_body", MISSION_BODY),
    ("vision_title", VISION_TITLE),
    ("vision_body", VISION_BODY),
]


def seed_mission_vision_blocks(apps, schema_editor):
    SiteBlock = apps.get_model("database", "SiteBlock")
    for block_key, content in BLOCKS:
        SiteBlock.objects.update_or_create(
            block_key=block_key,
            defaults={"content": content, "is_active": True},
        )


def remove_mission_vision_blocks(apps, schema_editor):
    SiteBlock = apps.get_model("database", "SiteBlock")
    keys = [key for key, _ in BLOCKS]
    SiteBlock.objects.filter(block_key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0037_alter_fpo_annual_turnover"),
    ]

    operations = [
        migrations.RunPython(seed_mission_vision_blocks, remove_mission_vision_blocks),
    ]