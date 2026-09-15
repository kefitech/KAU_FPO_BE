"""
Seed the Chatbot Knowledge Base (Phase 1).

Idempotent — safe to re-run. Uses update_or_create keyed by `topic`.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge.py').read())
    seed_chatbot_knowledge()
    "
"""


def seed_chatbot_knowledge():
    from apps.database.models import ChatKnowledgeEntry

    print("=" * 60)
    print("SEEDING CHATBOT KNOWLEDGE BASE")
    print("=" * 60)

    entries = [
        # ── Getting started (public) ────────────────────────────────────
        {
            'topic': 'What is KAU-FPO Platform',
            'audiences': ['public', 'all'],
            'pages': ['/', '/about-us'],
            'body_en': (
                'KAU-FPO is a digital platform by Kerala Agricultural University that '
                'connects Farmer Producer Organizations (FPOs) with buyers, government schemes, '
                'expert advisors, and AI-based crop recommendations. It supports FPO '
                'registration, product listing, buyer verification, and DPR generation.'
            ),
            'keywords': 'about what platform overview introduction',
        },
        {
            'topic': 'How to register an FPO',
            'audiences': ['public', 'all'],
            'pages': ['/register', '/register?mode=fpo'],
            'body_en': (
                'To register an FPO on the KAU-FPO Platform, visit /register and choose '
                'the FPO option. Complete the eligibility check with your member count and '
                'business type, verify your phone number and email via OTP, then fill out '
                'the four-step wizard covering basic info, legal registration, business '
                'details, and bank details.'
            ),
            'keywords': 'signup sign up new account create',
        },
        {
            'topic': 'How to register as a buyer',
            'audiences': ['public', 'all'],
            'pages': ['/register', '/market-hub', '/register?mode=buyer'],
            'body_en': (
                'To buy from FPOs, visit /register?mode=buyer. Verify your phone number '
                'and email via OTP, set a password, and submit. Your buyer account will '
                'be reviewed by KAU admin within 1 to 2 business days. Once verified, '
                'you can log in and browse all FPO products.'
            ),
            'keywords': 'buyer signup buy products purchase external',
        },
        {
            'topic': 'Public market hub',
            'audiences': ['public', 'all'],
            'pages': ['/market-hub', '/'],
            'body_en': (
                'Anyone can browse FPO products, commodity prices, and demand opportunities '
                'at /market-hub without logging in. To submit a purchase inquiry, click any '
                'product and use the Inquire button — no account required.'
            ),
            'keywords': 'market hub browse products prices public',
        },
        {
            'topic': 'Contact KAU support',
            'audiences': ['public', 'all'],
            'pages': ['/contact-us'],
            'body_en': (
                'For help with the KAU-FPO Platform, email kau-fpo@kau.in or use the '
                'feedback form at /contact-us. KAU responds within 2 business days.'
            ),
            'keywords': 'contact help support email',
        },
        # ── FPO registration flow (FPO manager) ─────────────────────────
        {
            'topic': 'FPO eligibility requirements',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/register', '/fpo/register'],
            'body_en': (
                'To register, your FPO must have at least 10 members and a legal '
                'business structure (Companies Act, Producer Companies Act, Kerala '
                'Cooperative Societies Act, or similar). You will need your PAN, GST '
                '(if applicable), CIN (for companies), bank details, and a Kerala '
                'district address.'
            ),
            'keywords': 'eligibility requirements minimum members legal',
        },
        {
            'topic': 'Verify email during FPO registration',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/register*'],
            'body_en': (
                'A 6-digit OTP will be sent to your office email. Enter it within '
                '10 minutes to verify. You can request a new OTP up to 3 times per '
                '10-minute window. Both email and phone must be verified before you '
                'can submit your application.'
            ),
            'keywords': 'email otp verify code',
        },
        {
            'topic': 'Verify phone during FPO registration',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/register*'],
            'body_en': (
                'A 6-digit SMS OTP is sent to your office phone number. Enter it within '
                '10 minutes. Rate limited to 3 attempts per 10-minute window. Both email '
                'and phone verification are required to submit.'
            ),
            'keywords': 'phone sms otp mobile verify',
        },
        {
            'topic': 'Required documents for FPO submission',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/register*'],
            'body_en': (
                'Three documents are mandatory: FPO Registration Certificate, Bank Details '
                'proof (cancelled cheque or bank letter), and PAN Card. Optional: GST '
                'certificate, Signatory ID, Member List, Annual Report. PDF, JPG, or PNG. '
                'Max size 5 MB (10 MB for member list and annual report).'
            ),
            'keywords': 'documents upload certificate pan gst required',
        },
        {
            'topic': 'How to submit FPO application',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/register*', '/fpo/status'],
            'body_en': (
                'Complete all four wizard steps, verify both email and phone, upload the '
                'three required documents, and click Submit. After submission the '
                'application is auto-approved instantly — you will see the status change '
                'to APPROVED and receive an email and SMS confirmation.'
            ),
            'keywords': 'submit apply application status finalize',
        },
        {
            'topic': 'FPO application status',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/status', '/fpo/dashboard'],
            'body_en': (
                'View your application status at /fpo/status. Statuses: DRAFT (in progress), '
                'SUBMITTED (auto-approved instantly), APPROVED (active), INFO_REQUIRED '
                '(KAU needs more info), REJECTED (denied), or SUSPENDED. The timeline '
                'shows every status change.'
            ),
            'keywords': 'status application progress timeline',
        },
        # ── FPO portal (approved) ───────────────────────────────────────
        {
            'topic': 'FPO dashboard overview',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/dashboard'],
            'body_en': (
                'Your FPO dashboard shows your tier badge, application status, team summary, '
                'document verification status, and quick links to profile, recommendations, '
                'products, and settings.'
            ),
            'keywords': 'dashboard home overview',
        },
        {
            'topic': 'Request crop recommendation',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/recommendations'],
            'body_en': (
                'Go to /fpo/recommendations and click Request Recommendation. The AI '
                'analyses your zone, soil, and season to suggest suitable crops with '
                'reasoning. Generation takes about a minute. Only available after FPO '
                'is approved and if the FPO is located inside Kerala.'
            ),
            'keywords': 'recommendation ai crop suggest predict',
        },
        {
            'topic': 'Generate a DPR',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/dpr*'],
            'body_en': (
                'Go to /fpo/dpr and click New Project. Fill in the wizard sections (project '
                'basics, location, product details, finance, etc.), then click Generate '
                'to produce a PDF Detailed Project Report. AI narrative sections are '
                'auto-generated but editable.'
            ),
            'keywords': 'dpr detailed project report pdf generate',
        },
        {
            'topic': 'Invite team member',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/team', '/fpo/settings'],
            'body_en': (
                'From /fpo/team click Invite. Enter their name, email, and phone. A temporary '
                'password is emailed to them; they will be prompted to change it on first '
                'login. There is no limit on the number of team members you can invite.'
            ),
            'keywords': 'team invite add member user',
        },
        {
            'topic': 'FPO register as buyer',
            'audiences': ['fpo_manager', 'all'],
            'pages': ['/fpo/buyer-directory'],
            'body_en': (
                'FPOs can also buy from other FPOs. Visit /fpo/buyer-directory and click '
                'Register as Buyer. Your registration will be reviewed by KAU admin. Once '
                'approved, browse products the same way external buyers do.'
            ),
            'keywords': 'fpo buyer buy other fpos',
        },
        # ── Buyer portal ────────────────────────────────────────────────
        {
            'topic': 'Buyer application under review',
            'audiences': ['external_buyer', 'all'],
            'pages': ['/buyer/status', '/buyer/pending'],
            'body_en': (
                'KAU admin typically verifies buyer accounts within 1 to 2 business days. '
                'You will receive an email confirmation once verified. Until then you can '
                'log out and browse the public market hub at /market-hub.'
            ),
            'keywords': 'pending review verify wait status buyer',
        },
        {
            'topic': 'Browse FPO products as buyer',
            'audiences': ['external_buyer', 'all'],
            'pages': ['/buyer/products'],
            'body_en': (
                'Verified buyers can browse all FPO products at /buyer/products. Filter by '
                'commodity, price range, and quantity. Click a product to see FPO details '
                'and quantities available.'
            ),
            'keywords': 'buyer browse products search commodity price',
        },
        {
            'topic': 'Complete buyer profile',
            'audiences': ['external_buyer', 'all'],
            'pages': ['/buyer/dashboard'],
            'body_en': (
                'On your buyer dashboard, complete your profile by selecting your district '
                'and the commodities you are interested in. This helps FPOs match you with '
                'relevant products.'
            ),
            'keywords': 'buyer profile complete commodities district',
        },
        # ── Admin ────────────────────────────────────────────────────────
        {
            'topic': 'Approve pending FPO application',
            'audiences': ['super_admin', 'sub_admin'],
            'pages': ['/admin/applications*'],
            'body_en': (
                'Open /admin/applications, filter by SUBMITTED status, and open a row. '
                'Verify all documents are marked verified in the Documents tab, then click '
                'Approve. Approval triggers an email + SMS to the FPO.'
            ),
            'keywords': 'admin approve fpo application verify',
        },
        {
            'topic': 'Verify buyer account',
            'audiences': ['super_admin', 'sub_admin'],
            'pages': ['/admin/buyers*'],
            'body_en': (
                'Open /admin/buyers, filter by Pending status, review the buyer\'s details, '
                'and click Verify. This activates their login and lets them browse FPO '
                'products. You can also Reject with a reason.'
            ),
            'keywords': 'admin verify approve buyer external',
        },
        {
            'topic': 'Add crop knowledge base entry',
            'audiences': ['super_admin'],
            'pages': ['/admin/crop-package-of-practices*'],
            'body_en': (
                'Go to /admin/crop-package-of-practices and click Add. Enter the crop name '
                '(must match ML predicted names), season, varieties, spacing, and other '
                'PoP sections. Save as inactive first, review, then activate.'
            ),
            'keywords': 'crop pop knowledge base add package practices',
        },
        {
            'topic': 'Manage crop zone eligibility',
            'audiences': ['super_admin'],
            'pages': ['/admin/crop-zone-profiles*'],
            'body_en': (
                'Crop zone profiles at /admin/crop-zone-profiles control which crops the '
                'AI recommends per KAU physiographic zone. Only active profiles affect '
                'recommendations. Editing exports the full active set to the ML service.'
            ),
            'keywords': 'zone profile crop eligibility ml recommendation',
        },
        # ── Common (all users) ──────────────────────────────────────────
        {
            'topic': 'Reset forgotten password',
            'audiences': ['public', 'all'],
            'pages': ['/v1/login', '/forgot-password'],
            'body_en': (
                'On the login page click Forgot Password. Enter your email — you will '
                'receive a reset link valid for 15 minutes. FPO users receive an SMS OTP '
                'instead. Follow the link or enter the OTP to set a new password.'
            ),
            'keywords': 'forgot password reset link email otp',
        },
        {
            'topic': 'Change password when logged in',
            'audiences': ['all'],
            'pages': ['/fpo/settings', '/admin/settings*'],
            'body_en': (
                'From your account settings, click Change Password. Enter your current '
                'password and the new one twice. New password must be at least 8 characters '
                'with an uppercase, lowercase, digit, and special character.'
            ),
            'keywords': 'change password update security',
        },
        {
            'topic': 'Switch language English Malayalam',
            'audiences': ['public', 'all'],
            'pages': [],
            'body_en': (
                'Click the language switcher (EN/ML) at the top-right of any page. Your '
                'preference is saved to your account when logged in.'
            ),
            'keywords': 'language malayalam english switch translate',
        },
        {
            'topic': 'Two factor authentication',
            'audiences': ['super_admin', 'sub_admin'],
            'pages': ['/settings/security', '/admin/settings/security'],
            'body_en': (
                'Super admins and sub-admins must enable 2FA. From your account settings '
                'go to Security, scan the QR code with Google Authenticator, and enter '
                'the code to activate. Save your backup codes securely.'
            ),
            'keywords': '2fa two factor authenticator qr backup',
        },
        {
            'topic': 'View notifications',
            'audiences': ['all'],
            'pages': [],
            'body_en': (
                'Click the bell icon at the top-right to open your inbox. You will see '
                'in-app notifications for application status changes, approvals, '
                'recommendations, and system announcements.'
            ),
            'keywords': 'notification bell inbox alerts',
        },
        {
            'topic': 'Log out of the platform',
            'audiences': ['all'],
            'pages': [],
            'body_en': (
                'Click your avatar at the top-right and choose Logout. This ends your '
                'session and clears authentication cookies. You will be redirected to '
                'the login page.'
            ),
            'keywords': 'logout log out signout exit',
        },
        {
            'topic': 'Search across the platform',
            'audiences': ['all'],
            'pages': [],
            'body_en': (
                'Most list pages have a search bar at the top. Type at least 2 characters '
                'to filter. Some pages also let you filter by status, category, or district '
                'using dropdowns.'
            ),
            'keywords': 'search filter find lookup',
        },
    ]

    created_count = 0
    updated_count = 0
    for entry in entries:
        obj, created = ChatKnowledgeEntry.objects.update_or_create(
            topic=entry['topic'],
            defaults={
                'audiences':     entry['audiences'],
                'pages':         entry.get('pages', []),
                'body_en':       entry['body_en'],
                'keywords':      entry.get('keywords', ''),
                'is_active':     True,
                'display_order': entry.get('display_order', 0),
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
        marker = 'CREATED' if created else 'UPDATED'
        print(f"  {marker}  {obj.topic}")

    print("=" * 60)
    print(f"✅ Done. {created_count} created, {updated_count} updated. Total: {ChatKnowledgeEntry.objects.count()}")
    print("=" * 60)
