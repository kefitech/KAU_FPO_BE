# KAU-FPO Phase 2 — Team Developer Guides

One file per developer. Read your file before writing a single line of code.

| Developer | File | Modules |
|-----------|------|---------|
| Athul (Lead) | [ATHUL.md](ATHUL.md) | P2-07 DPR Generation |
| Aravind | [ARAVIND.md](ARAVIND.md) | P2-05 GIS + P2-06 Crop Recommendations |
| Arunima | [ARUNIMA.md](ARUNIMA.md) | P2-11 Marketplace + P2-12 Market Hub + P2-14 Marketing |
| Jobin | [JOBIN.md](JOBIN.md) | P2-01 Row-Level Security + P2-02 Govt Portal + P2-03 CBBO + P2-08 Expert Booking |
| Aleena | [ALEENA.md](ALEENA.md) | P2-09 Analytics + P2-10 Chatbot + P2-04 Auto-Translate + P2-13 WhatsApp |

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
