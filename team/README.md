# KAU-FPO Phase 2 — Team Developer Guides

One file per developer. Read your file before writing a single line of code.

| Developer | File | Modules |
|-----------|------|---------|
| Athul (Lead) | [ATHUL.md](ATHUL.md) | P2-07 DPR Generation |
| Aravind | [ARAVIND.md](ARAVIND.md) | P2-05 GIS + P2-06 Crop Recommendations |
| Arunima | [ARUNIMA.md](ARUNIMA.md) | P2-11 Marketplace + P2-12 Market Hub + P2-14 Marketing |
| Jobin | [JOBIN.md](JOBIN.md) | P2-01 Row-Level Security + P2-02 Govt Portal + P2-03 CBBO + P2-08 Expert Booking |
| Aleena | [ALEENA.md](ALEENA.md) | P2-09 Analytics + P2-10 Chatbot + P2-04 Auto-Translate + P2-13 WhatsApp |

## Local Machine Setup — Do This Before Anything Else

### Step 1 — Install system packages (Ubuntu/Debian)

Required for GeoDjango (GIS maps). Without these, even importing GIS models will fail.

```bash
sudo apt-get update
sudo apt-get install -y \
  libgdal-dev \
  libgeos-dev \
  libproj-dev \
  postgresql-12-postgis-3 \
  postgresql-12-postgis-3-scripts \
  binutils
```

### Step 2 — Clone the repo and set up Python environment

```bash
git clone <repo-url>
cd kau-fpo-backend

python3 -m venv venv
source venv/bin/activate
pip install -r requirements/development.txt
```

### Step 3 — Set up local database

```bash
# Create the database (replace credentials as needed)
createdb -U postgres kau_fpo

# Enable PostGIS — MUST be done as superuser, BEFORE running migrations
sudo -u postgres psql -p 5432 -d kau_fpo -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

> If your PostgreSQL runs on a non-standard port (e.g. 5434), add `-p 5434`.

### Step 4 — Configure environment

```bash
# Copy the example env (ask Athul for actual values)
cp .env.example .env
# Edit .env with your local DB credentials
```

### Step 5 — Run migrations

```bash
source venv/bin/activate
python manage.py migrate
```

Confirm it runs with no errors before touching any code.

### Step 6 — Run seed scripts

```bash
# Translations
python manage.py shell -c "exec(open('scripts/seed_translations.py').read()); seed_translations()"

# Master data (dropdowns)
python manage.py shell -c "exec(open('scripts/seed_fpo_master_data.py').read()); seed_fpo_master_data()"

# Menu items
python manage.py shell -c "exec(open('scripts/seed_menu.py').read()); seed_menu()"
```

> Full seeding guide: `scripts/SEEDING_GUIDE.md`

---

## Git Workflow — Everyone Follows This

```
main        ← production only — never push here directly
develop     ← integration branch — all PRs merge here
feature/*   ← your working branch
```

### Daily flow

```bash
# Start of day — always pull develop first
git checkout develop
git pull origin develop

# Create your feature branch
git checkout -b feature/p2-07-dpr-wizard

# Work, commit often
git add apps/fpo/api/dpr.py
git commit -m "feat: add DPR wizard step 1-4 endpoints"

# Push your branch
git push origin feature/p2-07-dpr-wizard

# When done — raise PR to develop on GitHub
# Never push to main
```

### Commit message format

```
feat: short description of what you added
fix: short description of what you fixed
```

Examples:
```
feat: add expert booking confirmation endpoint
feat: add AnalyticsSnapshot Celery task
fix: wrong pagination class on marketplace listing
```

### PR rules
- PR title = same as your last commit message
- Always target `develop` branch — never `main`
- Tag Athul as reviewer
- PR must pass with no migration conflicts before merging
