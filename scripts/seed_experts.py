"""
Seed Expert Directory
========================
15 KAU expert persons from KAU RCD document (Expert persons.docx)

Usage:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_experts.py').read())
    seed_experts()
    "
"""

from apps.database.models.schemes import Expert, ExpertCategory


EXPERTS = [
    {
        'order': 1,
        'name_en': 'Dr. K. P. Sudheer',
        'designation': 'Professor & Head, Department of Agricultural Engineering; Head, RAFTAAR – R-ABI Project',
        'organisation': 'College of Agriculture, Vellanikkara, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Agricultural Engineering, Agribusiness Incubation, Entrepreneurship Development',
        'secondary_expertise': 'Agri-Startups, Business Incubation, Innovation Management, Technology Commercialization',
        'email': 'kp.sudheer@kau.in',
        'phone': '',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 2,
        'name_en': 'Dr. Prema A.',
        'designation': 'Professor & Head, Department of Agricultural Economics; Padmasree Paul Pothen IFFCO Professor Chair',
        'organisation': 'College of Agriculture, Vellanikkara, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Agricultural Economics, Agribusiness Management',
        'secondary_expertise': 'Farmer Producer Organizations (FPOs), Agricultural Policy, Project Appraisal, Rural Development',
        'email': 'prema.a@kau.in',
        'phone': '9446319848',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 3,
        'name_en': 'Dr. Anil Kuruvilla',
        'designation': 'Professor & Head, Department of Agricultural Economics',
        'organisation': 'College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Economics, Agricultural Finance',
        'secondary_expertise': 'Producer Organizations, Agribusiness Development, Rural Credit, Project Evaluation',
        'email': 'anil.kuruvila@kau.in',
        'phone': '9497233293',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 4,
        'name_en': 'Dr. S. Helen',
        'designation': 'Professor & Head, Central Training Institute',
        'organisation': 'Central Training Institute, Mannuthy, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Training and Capacity Building',
        'secondary_expertise': 'Human Resource Development, Institutional Strengthening, Leadership Development',
        'email': 'helen.s@kau.in',
        'phone': '9446142552',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 5,
        'name_en': 'Dr. Allan Thomas',
        'designation': 'Professor & Head, Department of Agricultural Extension; Founding Director K-AgTech LaunchPad',
        'organisation': 'College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Extension Education, Agri-based startup launch related incubation',
        'secondary_expertise': 'Farmer Organizations, Community Mobilization, Participatory Rural Development',
        'email': 't.allan@kau.in',
        'phone': '9447051292',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 6,
        'name_en': 'Dr. Giggin T.',
        'designation': 'Assistant Professor',
        'organisation': 'Communication Centre, Mannuthy, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Animal Husbandry Extension and Agricultural Communication',
        'secondary_expertise': 'Digital Extension, ICT-based Advisory Services, Knowledge Dissemination',
        'email': 'giggin.t@kau.in',
        'phone': '9847335759',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 7,
        'name_en': 'Dr. Sulaja O. R.',
        'designation': 'Assistant Professor',
        'organisation': 'Communication Centre, Mannuthy, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Agricultural Communication and Extension Education',
        'secondary_expertise': 'Knowledge Management, Digital Content Development, Extension Communication',
        'email': 'sulaja.or@kau.in',
        'phone': '9847813402',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 8,
        'name_en': 'Dr. Jayalakshmi G.',
        'designation': 'Senior Scientist & Head',
        'organisation': 'Krishi Vigyan Kendra, Kottayam, Kerala Agricultural University',
        'district': 'KTM',
        'primary_expertise': 'Agricultural Extension and Technology Transfer',
        'secondary_expertise': 'Farmer Capacity Building, Skill Development, Advisory Services',
        'email': 'kvkkottayam@kau.in',
        'phone': '8281705041',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 9,
        'name_en': 'Dr. Sreeram V.',
        'designation': 'Assistant Professor',
        'organisation': 'Regional Agricultural Research Station, Ambalavayal, Kerala Agricultural University',
        'district': 'WYD',
        'primary_expertise': 'Agricultural Research and Production Systems',
        'secondary_expertise': 'Sustainable Farming Systems, Technology Assessment, Crop Production',
        'email': 'sreeram.vishnu@kau.in',
        'phone': '9544769363',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 10,
        'name_en': 'Dr. Parvathi A.',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Extension, College of Agriculture, Vellanikkara, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Agricultural Extension Education',
        'secondary_expertise': 'Farmer Producer Organizations, Capacity Building, Institutional Development',
        'email': 'parvathi.a@kau.in',
        'phone': '7559806723',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 11,
        'name_en': 'Dr. Darsana S.',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Extension, College of Agriculture, Vellanikkara, Kerala Agricultural University',
        'district': 'TSR',
        'primary_expertise': 'Agricultural Extension Education',
        'secondary_expertise': 'Community Institutions, Participatory Approaches, Leadership Development',
        'email': 'darsana.s@kau.in',
        'phone': '9605103982',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 12,
        'name_en': 'Dr. Aswathy Vijayan',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Economics, College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Economics',
        'secondary_expertise': 'Financial Analysis, Agribusiness Planning, Project Evaluation',
        'email': 'aswathy.v@kau.in',
        'phone': '9847908870',
        'category': ExpertCategory.SCIENTIST,
    },
    {
        'order': 13,
        'name_en': 'Dr. Gopika Somanath',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Economics, College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Extension Education',
        'secondary_expertise': 'Farmer Producer Organizations, Agribusiness Development, Rural Institutions',
        'email': 'gopika.s@kau.in',
        'phone': '9746932564',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 14,
        'name_en': 'Dr. Smitha S.',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Extension, College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Extension Education',
        'secondary_expertise': 'Farmer Capacity Building, Community Organizations, Training Methodologies',
        'email': 'smitha.s@kau.in',
        'phone': '8136855008',
        'category': ExpertCategory.TRAINER,
    },
    {
        'order': 15,
        'name_en': 'Dr. Aparna Radhakrishnan',
        'designation': 'Assistant Professor',
        'organisation': 'Department of Agricultural Extension, College of Agriculture, Vellayani, Kerala Agricultural University',
        'district': 'TVM',
        'primary_expertise': 'Agricultural Extension Education',
        'secondary_expertise': 'Farmer Producer Organizations, Leadership Development, Institutional Strengthening',
        'email': 'aparna.r@kau.in',
        'phone': '8468990086',
        'category': ExpertCategory.TRAINER,
    },
]


def seed_experts():
    created = 0
    updated = 0

    for data in EXPERTS:
        obj, was_created = Expert.objects.update_or_create(
            email=data['email'],
            defaults={k: v for k, v in data.items() if k != 'email'},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    print(f'Experts seeded: {created} created, {updated} updated. Total: {Expert.objects.count()}')
