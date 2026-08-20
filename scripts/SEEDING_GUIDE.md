# KAU-FPO Platform — Data Seeding Guide

> Read this before writing any seed script for a Phase 2 module.
> The platform is multilingual — every piece of user-visible text must be seeded
> into the Translation table, not hardcoded in Python or TypeScript.

---

## How to Run Any Seed Script

**Always use this pattern.** Piping with `<` swallows all output — you will not see errors.

```bash
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/<script_name>.py').read())
<function_name>()
"
```

All seeds are **idempotent** — safe to re-run at any time. They use `update_or_create`,
so re-running applies the latest values without creating duplicates.

---

## All Seed Scripts — What They Do and When to Run

| Script | Function to Call | Run When |
|--------|-----------------|----------|
| `seed_translations.py` | `seed_translations()` | First setup + whenever new API message keys are added |
| `seed_fpo_master_data.py` | `seed_fpo_master_data()` | First setup + whenever a new dropdown category is added |
| `seed_menu.py` | `seed_menu()` | First setup + whenever a new page/sidebar item is added |
| `seed_notification_templates.py` | `seed_notification_templates()` | First setup + whenever a new notification event is added |
| `seed_ml_ui_translations.py` | `seed_ml_ui_translations()` | Run after seed_translations to add Malayalam UI strings |
| `seed_bank_name_ml_translations.py` | (run directly) | Run after seed_fpo_master_data to add ML bank names |
| `seed_cms_ml.py` | (run directly) | CMS content Malayalam translations |
| `seed_district_block_ml.py` | (run directly) | Malayalam translations for districts/blocks |
| `seed_tier_framework.py` | (run directly) | Tier assessment questions (28 questions, 5 domains) |
| `seed_experts.py` | (run directly) | Sample expert data for testing |
| `seed_schemes.py` | (run directly) | Sample scheme data for testing |
| `seed_fpo_permissions.py` | (run directly) | FPO role action permission matrix |

**First-time setup order (run in this exact sequence):**

```bash
# Step 1 — Languages + API message translations
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_translations.py').read())
seed_translations()
"

# Step 2 — Malayalam UI strings (run after seed_translations)
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_ml_ui_translations.py').read())
seed_ml_ui_translations()
"

# Step 3 — All dropdown master data (legal structure, blocks, commodities, banks)
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_fpo_master_data.py').read())
seed_fpo_master_data()
"

# Step 4 — Malayalam names for banks + districts/blocks
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_bank_name_ml_translations.py').read())
"
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_district_block_ml.py').read())
"

# Step 5 — Sidebar menu items
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_menu.py').read())
seed_menu()
"

# Step 6 — Notification template codes + templates
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_notification_templates.py').read())
seed_notification_templates()
"

# Step 7 — Tier framework questions
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_tier_framework.py').read())
"

# Step 8 — FPO action permissions matrix
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_fpo_permissions.py').read())
"
```

---

## The Translation System — How It Works

Everything user-visible goes through the Translation table, never hardcoded.

**Three layers of translatable content:**

| Layer | Category | Used by | Example key |
|-------|----------|---------|-------------|
| API messages | `auth`, `admin`, `fpo`, `common`, `dpr`, etc. | Backend → `t('dpr.project_created', lang)` | `dpr.project_created` |
| UI labels | `ui` | Frontend → `useTranslations('dpr_wizard')` | `dpr_wizard.section_title` |
| Dropdown names | same code as MasterLookup category | Frontend + Backend → `lookup.get_name(lang)` | `commodity.rice` |

**Key format rule — always `category.key`:**
```python
# ✅ Correct
t('dpr.project_created', language='ml')
t('common.permission_denied', language='en')

# ❌ Wrong — TranslationService rejects bare keys
t('project_created')
```

---

## How to Add Translations for a New Phase 2 Module

### Step 1 — Add a new category to seed_translations.py

Open `scripts/seed_translations.py`, find the `create_categories()` function and add:

```python
{
    'code': 'dpr',            # ← your module code
    'name': 'DPR Management',
    'description': 'Project creation, section management, PDF generation messages',
    'display_order': 10,
},
```

### Step 2 — Add message keys to seed_translations.py

In the same file, add a new seeding function for your module:

```python
def seed_dpr_translations(languages):
    """Seed DPR module API response messages"""
    from apps.database.models import TranslationCategory, Translation

    category = TranslationCategory.objects.get(code='dpr')
    lang_en = languages['en']
    lang_ml = languages['ml']

    messages = [
        # (key,                      English,                            Malayalam)
        ('project_created',         'DPR project created successfully', 'DPR പ്രൊജക്ട് വിജയകരമായി സൃഷ്ടിച്ചു'),
        ('project_updated',         'Project updated successfully',     'പ്രൊജക്ട് വിജയകരമായി അപ്ഡേറ്റ് ചെയ്തു'),
        ('section_saved',           'Section saved',                    'വിഭാഗം സേവ് ചെയ്തു'),
        ('pdf_generated',           'DPR PDF generated successfully',   'DPR PDF വിജയകരമായി ജനറേറ്റ് ചെയ്തു'),
        ('not_found',               'DPR project not found',            'DPR പ്രൊജക്ട് കണ്ടെത്തിയില്ല'),
        ('submit_validation_failed','Please complete all required sections before submitting',
                                                                        'സമർപ്പിക്കുന്നതിന് മുൻപ് എല്ലാ ആവശ്യമായ വിഭാഗങ്ങളും പൂർത്തിയാക്കുക'),
    ]

    for key, en_val, ml_val in messages:
        Translation.objects.update_or_create(
            category=category, key=key, language=lang_en,
            defaults={'value': en_val, 'is_verified': True}
        )
        Translation.objects.update_or_create(
            category=category, key=key, language=lang_ml,
            defaults={'value': ml_val, 'is_verified': True}
        )
        print(f"  ✅ {category.code}.{key}")
```

Then call it from `seed_translations()`:
```python
def seed_translations():
    languages = {lang.code: lang for lang in create_languages()}
    create_categories()
    ...
    seed_dpr_translations(languages)   # ← add this line
```

### Step 3 — Add UI label keys

UI labels are things the **frontend** displays: page titles, button text, field labels, table headers.
They live in the `ui` category with a screen prefix in the key.

```python
def seed_dpr_ui_translations(languages):
    from apps.database.models import TranslationCategory, Translation

    category = TranslationCategory.objects.get(code='ui')
    lang_en = languages['en']
    lang_ml = languages['ml']

    ui_labels = [
        # Screen: dpr_wizard — the 23-section data entry wizard
        ('dpr_wizard.title',                'Create DPR Project',           'DPR പ്രൊജക്ട് സൃഷ്ടിക്കുക'),
        ('dpr_wizard.project_name_label',   'Project Name',                  'പ്രൊജക്ട് നാമം'),
        ('dpr_wizard.component_label',      'Select Components',             'ഘടകങ്ങൾ തിരഞ്ഞെടുക്കുക'),
        ('dpr_wizard.save_and_continue',    'Save & Continue',               'സേവ് ചെയ്ത് തുടരുക'),
        ('dpr_wizard.calculate_btn',        'Calculate Financials',          'സാമ്പത്തിക കണക്കുകൂട്ടൽ'),
        ('dpr_wizard.submit_btn',           'Generate DPR',                  'DPR ജനറേറ്റ് ചെയ്യുക'),
        ('dpr_wizard.readiness_score',      'Readiness Score',               'തൈയ്യാർ സ്കോർ'),

        # Screen: dpr_list — list of all DPR projects for this FPO
        ('dpr_list.title',                  'My DPR Projects',               'എന്റെ DPR പ്രൊജക്ടുകൾ'),
        ('dpr_list.empty',                  'No projects yet. Create your first DPR.',
                                                                              'ഇതുവരെ പ്രൊജക്ടുകളൊന്നുമില്ല. നിങ്ങളുടെ ആദ്യ DPR സൃഷ്ടിക്കുക.'),
        ('dpr_list.status_draft',           'Draft',                         'ഡ്രാഫ്റ്റ്'),
        ('dpr_list.status_complete',        'Complete',                      'പൂർണ്ണം'),
    ]

    for key, en_val, ml_val in ui_labels:
        Translation.objects.update_or_create(
            category=category, key=key, language=lang_en,
            defaults={'value': en_val, 'is_verified': True}
        )
        Translation.objects.update_or_create(
            category=category, key=key, language=lang_ml,
            defaults={'value': ml_val, 'is_verified': True}
        )
```

**Screen naming rule:** prefix with the page name, separated by `.`
- `dpr_wizard.` → keys for the DPR creation wizard
- `dpr_list.` → keys for the DPR list page
- `recommendations.` → keys for the crop recommendation screen
- `marketplace.` → keys for product listing page

The frontend fetches them via:
```typescript
const { t } = useTranslations("dpr_wizard,dpr_list");  // matches the prefix
// t["dpr_wizard.title"] → "DPR പ്രൊജക്ട് സൃഷ്ടിക്കുക"
```

### Step 4 — Run the updated seed

```bash
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_translations.py').read())
seed_translations()
"
```

---

## How to Seed Dropdown Data (MasterLookup)

Dropdowns are stored in `MasterLookup`. Their display names live in the `Translation` table
under a category code that matches `MasterLookup.category`.

**Pattern used in `seed_fpo_master_data.py`:**

```python
def seed_dpr_master_data():
    from apps.core.models.generic import MasterLookup
    from apps.database.models import Language, TranslationCategory, Translation

    lang_en = Language.objects.get(code='en')
    lang_ml = Language.objects.get(code='ml')

    def _seed_lookup(category, entries, category_label, desc):
        cat, _ = TranslationCategory.objects.update_or_create(
            code=category,
            defaults={'name': category_label, 'description': desc},
        )
        for i, entry in enumerate(entries):
            MasterLookup.objects.update_or_create(
                category=category, code=entry['code'],
                defaults={'display_order': i, 'is_active': True},
            )
            Translation.objects.update_or_create(
                category=cat, key=entry['code'], language=lang_en,
                defaults={'value': entry['en']},
            )
            Translation.objects.update_or_create(
                category=cat, key=entry['code'], language=lang_ml,
                defaults={'value': entry.get('ml', entry['en'])},
            )
        print(f"  {category}: {len(entries)} entries seeded")

    # Example: DPR component types
    _seed_lookup('dpr_component', [
        {'code': 'processing_unit',   'en': 'Processing Unit',     'ml': 'പ്രോസസ്സിംഗ് യൂണിറ്റ്'},
        {'code': 'storage',           'en': 'Storage Facility',    'ml': 'സംഭരണ സൗകര്യം'},
        {'code': 'transport',         'en': 'Transport',           'ml': 'ഗതാഗതം'},
        {'code': 'irrigation',        'en': 'Irrigation System',   'ml': 'ജലസേചന സംവിധാനം'},
        {'code': 'packaging',         'en': 'Packaging Unit',      'ml': 'പാക്കേജിംഗ് യൂണിറ്റ്'},
    ], 'DPR Components', 'Types of components in a DPR project')
```

**Fetching in serializers/views:**
```python
from apps.core.models.generic import MasterLookup

components = MasterLookup.objects.filter(category='dpr_component', is_active=True)
# Each item has: .code, .get_name(language='ml') → reads Translation table
```

**Public API** (frontend dropdown population):
```
GET /api/public/master-data/?category=dpr_component&lang=ml
```
Returns: `[{ "code": "processing_unit", "name": "പ്രോസസ്സിംഗ് യൂണിറ്റ്" }, ...]`

---

## How to Seed Notification Templates

When a new event needs to trigger an email/SMS/in-app notification, add it to
`scripts/seed_notification_templates.py`.

**Format:**
```python
TEMPLATE_CODES = [
    # (code,              channel,  description,                           variables)
    ('dpr_generated',    'email',  'DPR PDF ready notification',         ['user_name', 'project_name', 'download_link']),
    ('dpr_generated',    'in_app', 'In-app: DPR PDF generated',          ['user_name', 'project_name']),
    ('booking_confirmed','email',  'Expert booking confirmed',            ['user_name', 'expert_name', 'slot_date', 'slot_time']),
    ('booking_confirmed','sms',    'Expert booking confirmed SMS',        ['user_name', 'expert_name', 'slot_date']),
    ('booking_reminder', 'email',  'Reminder 24h before expert booking', ['user_name', 'expert_name', 'slot_date', 'slot_time']),
    ('booking_reminder', 'sms',    'Reminder SMS 24h before booking',    ['user_name', 'slot_date']),
]
```

**Template bodies** are seeded in `TEMPLATES` dict:
```python
TEMPLATES = {
    ('dpr_generated', 'email', 'en'): {
        'subject': 'Your DPR is Ready — {{project_name}}',
        'body': """<p>Dear <strong>{{user_name}}</strong>,</p>
<p>Your DPR for project <strong>{{project_name}}</strong> has been generated successfully.</p>
<p>Click the button below to download the PDF.</p>""",
    },
    ('dpr_generated', 'email', 'ml'): {
        'subject': 'നിങ്ങളുടെ DPR തയ്യാർ — {{project_name}}',
        'body': """<p>പ്രിയ <strong>{{user_name}}</strong>,</p>
<p><strong>{{project_name}}</strong> പ്രൊജക്ടിനായുള്ള DPR വിജയകരമായി ജനറേറ്റ് ചെയ്തു.</p>""",
    },
    ('dpr_generated', 'in_app', 'en'): {
        'subject': 'DPR Ready',
        'body':    'Your DPR for {{project_name}} is ready to download.',
    },
    ...
}
```

Re-run seed after adding:
```bash
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_notification_templates.py').read())
seed_notification_templates()
"
```

---

## How to Seed Menu Items

Menu items appear in the sidebar and are role-filtered. They link to a translation key
for the label so the sidebar renders in Malayalam or English based on user preference.

Open `scripts/seed_menu.py` and add inside `seed_menu()`:

```python
# Phase 2 — FPO Portal new pages
seed_item('menu.fpo_dpr',             '/fpo/dpr',             'FileText',  [primary_group, secondary_group], order=6)
seed_item('menu.fpo_recommendations', '/fpo/recommendations', 'Lightbulb', [primary_group, secondary_group], order=7)
seed_item('menu.fpo_marketplace',     '/fpo/products',        'ShoppingCart', [primary_group],               order=8)
seed_item('menu.fpo_experts',         '/fpo/experts',         'Users',     [primary_group, secondary_group], order=9)

# Phase 2 — Admin new pages
seed_item('menu.admin_analytics',     '/admin/analytics',     'BarChart2', [super_admin_group, sub_admin_group], order=15)
seed_item('menu.admin_gis',           '/admin/gis',           'Map',       [super_admin_group],                  order=16)
```

Then add the corresponding translation keys in `seed_translations.py`:
```python
('menu.fpo_dpr',             'DPR Projects',         'DPR പ്രൊജക്ടുകൾ'),
('menu.fpo_recommendations', 'Crop Recommendations', 'കൃഷി ശുപാർശകൾ'),
('menu.fpo_marketplace',     'My Products',          'എന്റെ ഉൽപ്പന്നങ്ങൾ'),
('menu.fpo_experts',         'Expert Directory',     'വിദഗ്ദ്ധ ഡയറക്ടറി'),
('menu.admin_analytics',     'Analytics',            'അനലിറ്റിക്‌സ്'),
('menu.admin_gis',           'GIS Map',              'GIS മാപ്പ്'),
```

Re-run seeds:
```bash
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_translations.py').read())
seed_translations()
"
source venv/bin/activate && python manage.py shell -c "
exec(open('scripts/seed_menu.py').read())
seed_menu()
"
```

---

## Phase 2 — Seeding Checklist Per Module

Use this checklist when finishing each Phase 2 module. Do not mark a module done until
all seed steps are complete.

### P2-07 DPR (Lead)
- [ ] Add `dpr` translation category to `seed_translations.py`
- [ ] Seed API message keys — `dpr.project_created`, `dpr.section_saved`, `dpr.pdf_generated`, etc.
- [ ] Seed UI label keys — `dpr_wizard.*`, `dpr_list.*`
- [ ] Seed `dpr_component` MasterLookup (component types selectable in wizard)
- [ ] Seed notification templates — `dpr_generated` (email + in_app)
- [ ] Seed menu item — `menu.fpo_dpr` → `/fpo/dpr`

### P2-05 GIS + P2-06 Recommendations (Dev 2)
- [ ] Seed `agro_zone` MasterLookup (zone codes + EN/ML names)
- [ ] Seed `soil_type` MasterLookup (laterite, alluvial, red loam, etc.)
- [ ] Seed `season` MasterLookup (kharif, rabi, summer)
- [ ] Seed UI label keys — `recommendations.*`
- [ ] Seed notification templates — `recommendation_ready` (in_app + email)
- [ ] Seed menu item — `menu.fpo_recommendations`

### P2-11 Marketplace + P2-12 Market Hub (Dev 3)
- [ ] Seed `product_category` MasterLookup (vegetables, fruits, grains, spices, etc.)
- [ ] Seed `product_unit` MasterLookup (kg, MT, litre, dozen, etc.)
- [ ] Seed UI label keys — `marketplace.*`, `market_hub.*`
- [ ] Seed menu item — `menu.fpo_marketplace`

### P2-02 Government Portal + P2-03 CBBO (Dev 4)
- [ ] Seed UI label keys — `govt_portal.*`, `cbbo_portal.*`
- [ ] Seed menu items for government + CBBO portals (separate role groups)
- [ ] Seed notification templates — `training_session_created`, `report_submitted`

### P2-09 Analytics + P2-10 Chatbot (Dev 5)
- [ ] Seed UI label keys — `analytics.*`, `chatbot.*`
- [ ] Seed menu item — `menu.admin_analytics`
- [ ] Seed notification templates — `analytics_report_ready` (email)

---

## Adding a New Language (e.g. Tamil)

If KAU requests Tamil support later, add it to `seed_translations.py` and re-run:

```python
languages = [
    {'code': 'en', ...},
    {'code': 'ml', ...},
    {'code': 'ta', 'name': 'Tamil', 'native_name': 'தமிழ்', 'is_default': False,
     'is_active': True, 'display_order': 3, 'locale': 'ta_IN'},  # ← add this
]
```

Then go to the Django admin panel → Languages → activate Tamil.
All existing translation keys will initially have no Tamil value — they fall back to English.
Tamil values can be added via the admin panel Export/Import workflow (download xlsx → translate → upload).

**Zero code change needed anywhere** — the translation system is language-agnostic.

---

## How to Use Seeded Data on the Frontend

Once backend seeds are run, the frontend consumes the data through three channels.
Each type of seeded data has a specific API and hook.

---

### 1. UI Labels — `useTranslations(namespace)`

UI label keys (seeded under the `ui` category with a screen prefix) are fetched
using the `useTranslations` hook.

**File:** `src/hooks/use-translations.ts`

```typescript
import { useTranslations } from "@/hooks/use-translations";

function DprWizardPage() {
  // Pass the screen prefix(es) you seeded — comma-separated for multiple
  const { t, loading } = useTranslations("dpr_wizard,common");

  if (loading) return <Skeleton />;

  return (
    <div>
      <h1>{t["dpr_wizard.title"]}</h1>              {/* "DPR പ്രൊജക്ട് സൃഷ്ടിക്കുക" in ML */}
      <label>{t["dpr_wizard.project_name_label"]}</label>
      <button>{t["dpr_wizard.save_and_continue"]}</button>
    </div>
  );
}
```

**How it works under the hood:**
```
useTranslations("dpr_wizard,common")
  → GET /api/translations/public/?lang=ml&screen=dpr_wizard,common
  → Backend reads Translation table, returns grouped by screen prefix
  → Hook merges all screen groups into a flat { key: value } object
  → t["dpr_wizard.title"] → "DPR പ്രൊജക്ട് സൃഷ്ടിക്കുക"
```

**Language is automatic** — the hook reads `locale` from `useLocaleStore`, which the
user sets when they switch language. Re-fetches automatically on language change.

**Key rule:** the namespace you pass to `useTranslations()` must exactly match the
screen prefix in the seed script — `dpr_wizard` matches keys seeded as `dpr_wizard.*`.

---

### 2. Dropdown Data — `masterDataApi.get()`

MasterLookup items (seeded via `_seed_lookup()`) are fetched using `masterDataApi`.

**File:** `src/lib/api/master-data.ts`

```typescript
import { masterDataApi } from "@/lib/api/master-data";
import { useLocaleStore } from "@/stores/locale-store";

function DprComponentStep() {
  const locale = useLocaleStore((s) => s.locale);
  const [components, setComponents] = useState<MasterDataItem[]>([]);

  useEffect(() => {
    // Pass locale so API returns names in the current language
    masterDataApi.get("dpr_component", undefined, locale).then(setComponents);
  }, [locale]);

  return (
    <select>
      {components.map((c) => (
        <option key={c.code} value={c.code}>
          {c.name}   {/* "പ്രോസസ്സിംഗ് യൂണിറ്റ്" in ML, "Processing Unit" in EN */}
        </option>
      ))}
    </select>
  );
}
```

**What `masterDataApi.get()` accepts:**

| Param | Type | Example | Purpose |
|-------|------|---------|---------|
| `category` | `string` | `"dpr_component"` | Which MasterLookup category |
| `district` | `string \| undefined` | `"TRS"` | Filter blocks by district |
| `lang` | `string \| undefined` | `locale` | Language for display names |

**The API call it makes:**
```
GET /api/public/master-data/?category=dpr_component&lang=ml
→ [{ "code": "processing_unit", "name": "പ്രോസസ്സിംഗ് യൂണിറ്റ്" }, ...]
```

**Real usage from the existing codebase** (Step 4 of FPO registration):
```typescript
// From src/app/fpo/(wizard)/register/_components/step4-business.tsx
const locale = useLocaleStore((state) => state.locale);

useEffect(() => {
  masterDataApi.get("commodity").then(setCommodities);
  masterDataApi.get("bank_name", undefined, locale).then(setBankNames);
}, [locale]);
```

---

### 3. API Response Messages — Automatic (No Frontend Code Needed)

API messages (seeded under `auth`, `fpo`, `dpr`, `common`, etc.) are returned
directly in the response `message` field. The frontend just displays `response.data.message`.

```typescript
// In any API call handler
const { data } = await api.post("/dpr/projects/", payload);
toast.success(data.message);  // Shows "DPR പ്രൊജക്ട് വിജയകരമായി സൃഷ്ടിച്ചു" in ML
```

The backend reads `X-Language` header (set automatically by `apiClient`) and returns
the message in the correct language. Zero extra work on the frontend.

---

### 4. Sidebar Menu — Automatic (No Frontend Code Needed)

Menu items seeded in `seed_menu.py` are returned by `GET /api/auth/me/` after login.
The sidebar reads `user.menu` from `useAuthStore` and renders it — no hardcoded nav items.

```typescript
// From useAuthStore
const { user } = useAuthStore();
// user.menu = [{ label: "DPR Projects", path: "/fpo/dpr", icon: "FileText" }, ...]
// Already translated to the user's preferred language by the backend
```

If a new menu item is seeded and the user already logged in, they need to **log out and
log in again** for the new item to appear (menu comes from the login API response).

---

### Full Flow — Seeding a New Page End to End

Using DPR as an example — the complete journey from seed to UI:

```
Backend Dev                                    Frontend Dev
──────────────────────────────────────────     ──────────────────────────────────────────

1. Seed translation category 'dpr'
   seed_translations.py → seed_dpr_translations()

2. Seed UI labels with screen prefix
   'dpr_wizard.title' = 'Create DPR Project'  →  useTranslations("dpr_wizard")
   'dpr_wizard.title' = 'DPR പ്രൊജക്ട് ...'       t["dpr_wizard.title"]

3. Seed dropdown data
   _seed_lookup('dpr_component', [...])        →  masterDataApi.get("dpr_component", undefined, locale)
   EN: "Processing Unit"                          → renders in current language automatically
   ML: "പ്രോസസ്സിംഗ് യൂണിറ്റ്"

4. Seed API message keys
   'dpr.project_created' = 'DPR ...'          →  toast.success(response.data.message)
   Backend returns in X-Language automatically     No extra code needed

5. Seed notification template
   ('dpr_generated', 'email', 'en') + 'ml'    →  User receives email in their language
   Body uses {{project_name}} variable            automatically

6. Seed menu item
   seed_item('menu.fpo_dpr', '/fpo/dpr', ...)  →  Appears in sidebar after next login
   Translation: 'DPR Projects' / 'DPR പ്രൊജക്ടുകൾ'   No sidebar code changes needed
```

---

### Quick Reference — Which Hook / API for Which Seed Type

| Seeded data | Frontend usage | File |
|-------------|---------------|------|
| `ui` category keys (`dpr_wizard.*`) | `useTranslations("dpr_wizard")` → `t["dpr_wizard.title"]` | `src/hooks/use-translations.ts` |
| `MasterLookup` rows | `masterDataApi.get("dpr_component", undefined, locale)` | `src/lib/api/master-data.ts` |
| API message keys (`dpr.created`) | `response.data.message` — automatic | Returned by backend in every response |
| Menu items | `user.menu` from `useAuthStore()` — automatic | Set after login from `/api/auth/me/` |
| Notification templates | No frontend code — backend sends email/SMS/in-app | `send_notification()` in backend |

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Hardcoding `"Created successfully"` in a view | Use `t('module.created', language=lang)` |
| Hardcoding dropdown options in serializer `choices` | Use MasterLookup + Translation |
| Using bare key `t('created')` | Always `category.key` — `t('dpr.created')` |
| Putting UI label in `auth` category | UI labels go in `ui` category with screen prefix |
| Forgetting Malayalam for a new key | Seed English only if ML not available — it falls back gracefully, but add ML ASAP |
| Running seed with `<` pipe | Always use the `exec(open(...).read())` pattern — pipe swallows errors |
| Seeding `update_or_create` without `is_verified=True` | Unverified keys are hidden from public API |
| Passing wrong namespace to `useTranslations` | Namespace must exactly match the screen prefix used in the seed key |
| Not passing `locale` to `masterDataApi.get()` | Without `locale`, API returns English names regardless of user's language |
| Expecting new menu item without re-login | Menu is returned at login time — user must log out and back in |
