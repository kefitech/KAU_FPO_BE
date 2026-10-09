"""
Chatbot KB gap-fill — curated entries for the 128 weak-coverage questions
found by the Pass-1 retrieval audit (chatbot_coverage_pass1.xlsx,
2026-10-09). One entry answers a cluster of related tester questions.

Facts verified against code before writing (no guessed behaviour):
  * Tier cutoffs + domains      — apps/fpo/api/tier_assessment.py (A>=80,
    B>=65, C>=50, else D; 28 questions, 6 domains)
  * Scheme/training auto-hide   — apps/accounts/tasks.py + SubAdminConfig
    (scheme_expiry_days / training_expiry_days, default 5)
  * Inbox is read-only          — InboxViewSet has no delete
  * DPR defaults                — DPRConfig seed (12% discount, 10.5%/5y/
    12mo loan, 25.17% tax, 10/15/15 depreciation, moratorium serviced)
  * Booking has no video link / certificate fields — expert_booking.py

Landing-page education entries (DSC / MCA / MoA-AoA / share capital /
benefits) are general FPO-formation content — flagged for KAU review.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_kb_gap_fill.py').read())
    seed_chatbot_kb_gap_fill()
    "
Idempotent — update_or_create by topic.
"""

PUB = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
FPO = ['fpo_manager']
ADMIN = ['super_admin', 'sub_admin']
GOV = ['government']
CBBO = ['cbbo']

ENTRIES = [
    # ── Landing page / public ───────────────────────────────────────────
    dict(
        topic='Who can register — FPOs, not individual farmers',
        audiences=PUB,
        keywords='individual farmer register who can join membership eligibility benefits of joining FPO',
        body=(
            'Only Farmer Producer Organisations (FPOs) register on this platform — '
            'individual farmers cannot create an account directly. A farmer takes part '
            'by becoming a member (shareholder) of an FPO; the FPO\'s primary user then '
            'registers the organisation here. Benefits of joining an FPO include '
            'collective selling for better prices, shared processing and storage '
            'infrastructure, easier access to credit, subsidies and government schemes, '
            'training and expert guidance, and a share in the FPO\'s profits.'
        ),
    ),
    dict(
        topic='Registration — login first, then the 4-step wizard, then automatic approval',
        audiences=PUB,
        keywords='login before registration what happens after register account wizard steps approval application id',
        body=(
            'Yes — you first create a user account (name, email, phone, password) and '
            'log in; registration of the FPO itself then happens inside the portal '
            'through a 4-step wizard (basic details, location and contact, organisation '
            'details, bank and commodities). You verify the office email and phone by '
            'OTP, upload the three required documents, and submit. Approval is '
            'automatic on successful submission — you immediately receive an '
            'application ID and a confirmation by email and SMS, and the FPO dashboard '
            'unlocks.'
        ),
    ),
    dict(
        topic='Programme phases — Phase I and Phase II',
        audiences=PUB,
        keywords='phase I phase II programme phases what are phases rollout',
        body=(
            'The KAU-FPO Linkage Programme is delivered in two phases. Phase I covers '
            'the digital platform foundation: FPO registration and profiles, tier '
            'assessment, schemes and subsidies information, the expert directory, '
            'training coordination and the knowledge base. Phase II adds the advanced '
            'services: AI-based crop recommendations, GIS maps and agro-climatic zone '
            'intelligence, the produce marketplace with buyer connections, analytics '
            'dashboards, and portals for government officials and CBBO partners.'
        ),
    ),
    dict(
        topic='FPO company formation — DSC, MCA name reservation, MoA and AoA, Certificate of Incorporation',
        audiences=PUB,
        keywords='DSC digital signature certificate MCA reserve company name MoA AoA memorandum articles certificate of incorporation RoC producer company formation',
        body=(
            'These terms belong to registering a Producer Company before joining the '
            'platform. A DSC (Digital Signature Certificate) is the electronic '
            'signature a proposed director needs to sign company forms online. The '
            'company name is reserved through the MCA (Ministry of Corporate Affairs) '
            'portal using the RUN / SPICe+ service. The MoA (Memorandum of '
            'Association) states the company\'s objectives and the AoA (Articles of '
            'Association) its internal rules — both are filed at incorporation. The '
            'Certificate of Incorporation is issued by the Registrar of Companies '
            '(RoC) under the MCA once registration is approved; its CIN number is '
            'what you enter during platform registration.'
        ),
    ),
    dict(
        topic='Share capital of an FPO — what it is and whether it is refundable',
        audiences=PUB,
        keywords='share capital refundable member shares equity contribution withdraw',
        body=(
            'Share capital is the money members invest in the FPO in exchange for '
            'shares — it funds the organisation\'s operations and is distinct from '
            'fees or deposits. Shares in a producer company are normally not '
            'refundable on demand; a member who leaves typically transfers shares to '
            'another member or has them bought back as the FPO\'s articles and the '
            'Producer Companies provisions allow. Consult the FPO\'s own Articles of '
            'Association for the exact exit terms.'
        ),
    ),
    dict(
        topic='What is a DPR and how it helps with bank loans',
        audiences=PUB,
        keywords='DPR detailed project report purpose bank loan finance appraisal why needed',
        body=(
            'A DPR (Detailed Project Report) is the complete plan for a proposed '
            'project — the product, machinery, costs, funding sources, and ten-year '
            'financial projections (profit and loss, cash flow, balance sheet, DSCR, '
            'IRR and break-even). Banks and scheme agencies appraise loan and subsidy '
            'applications on the strength of the DPR. On this platform, a registered '
            'FPO builds its DPR through a guided wizard; the financial statements are '
            'auto-calculated and a bank-ready PDF is generated.'
        ),
    ),
    dict(
        topic='News, announcements and subsidy information on the website',
        audiences=PUB,
        keywords='latest news announcements where subsidy information government schemes NABARD grant notices',
        body=(
            'The latest announcements from KAU are shown in the Announcements section '
            'of the landing page, and curated news sources appear in the News section. '
            'Government scheme and subsidy information — eligibility, benefits and how '
            'to apply — is in the Schemes section. Check the Announcements list for '
            'any specific notice (for example a grant programme); if it is not listed '
            'there, no such announcement has been published on the platform.'
        ),
    ),
    dict(
        topic='Device and browser support',
        audiences=PUB,
        keywords='mobile phone browser supported chrome firefox resolution responsive tablet',
        body=(
            'The platform is a responsive web application: it works on mobile phones, '
            'tablets and desktops through a modern browser (current versions of '
            'Chrome, Edge, Firefox or Safari). No app installation is required and '
            'there is no fixed screen-resolution requirement — pages adapt to the '
            'screen size.'
        ),
    ),

    # ── FPO portal ──────────────────────────────────────────────────────
    dict(
        topic='FPO tier system — tiers, how the tier is decided, and how to improve',
        audiences=PUB,
        keywords='tier A B C D what tiers different tiers how decided grading score assessment 28 questions domains improve upgrade reach tier history previous year Q2 Q7 Q21 question numbers suggestions',
        pages=['/fpo/*'],
        body=(
            'FPOs are graded into tiers A, B, C and D. The grade comes from the '
            'annual tier self-assessment: 28 questions across six domains — '
            'Institutional Governance, Management Capacity, Membership Strength, '
            'Financial Strength, Infrastructure & Assets, and Business & Market '
            'Performance. Scores add up to 100; 80 or more is Tier A, 65–79 Tier B, '
            '50–64 Tier C, and below 50 Tier D. One assessment is made per financial '
            'year, and past years\' tiers are shown in the assessment history on your '
            'dashboard. The improvement tips shown after submission reference the '
            'question they come from — "Q2", "Q7", "Q21" are those question numbers. '
            'Tips can appear even for a domain where you scored full marks, because '
            'each tip is tied to an individual answer, not the domain total. To reach '
            'a higher tier, work through the tips and re-assess in the next financial '
            'year.'
        ),
    ),
    dict(
        topic='FPO team roles — Primary and Secondary users and their permissions',
        audiences=FPO + ADMIN,
        keywords='secondary role meaning primary user permissions what can user do team member rights matrix',
        pages=['/fpo/settings*'],
        body=(
            'The Primary user is the account that registered the FPO — the owner, '
            'with full access. Secondary users are team members the Primary user '
            'invites from Settings → Team; they log in with their own credentials '
            'and work on the same FPO. What a Secondary user can do (upload '
            'documents, edit the profile, manage the team, submit claims, and so on) '
            'is controlled by a permission matrix that the KAU admin configures per '
            'role. To see a specific team member\'s access, open Settings → Team; '
            'admins can view and change the role-permission matrix under Admin → '
            'FPO Permissions.'
        ),
    ),
    dict(
        topic='Notifications — types, the bell inbox, marking read, and why counts can differ',
        audiences=FPO + ADMIN + GOV + CBBO,
        keywords='notifications types email sms in-app bell unread mark all read delete notifications latest count mismatch category',
        body=(
            'You receive notifications three ways: email, SMS, and the in-app inbox '
            'behind the bell icon. They cover application status, team invitations, '
            'password and security events, bookings, buyer inquiries and training '
            'announcements. In the bell inbox you can open a notification to mark it '
            'read, or use "Mark all as read". Notifications cannot be deleted — the '
            'inbox is a permanent record, and older items simply age out of view. If '
            'a category count differs from the "All" total, refresh the page — the '
            'badge and the list update at slightly different moments. The assistant '
            'cannot read your personal inbox; open the bell icon to see your latest '
            'notifications and the unread count.'
        ),
    ),
    dict(
        topic='Buyer inquiries — where to see and reply',
        audiences=FPO,
        keywords='buyer inquiry reply respond new enquiry marketplace interest product question from buyer',
        body=(
            'When a buyer sends an inquiry about one of your products, you are '
            'notified and the inquiry appears in your marketplace / products area. '
            'Open the inquiry to read the buyer\'s message and respond; the buyer is '
            'notified of your reply. Responding promptly keeps your FPO visible and '
            'credible to buyers.'
        ),
    ),
    dict(
        topic='Trainings for FPOs — schedule, attendance and participation',
        audiences=FPO,
        keywords='training upcoming register attend who conducted participants session date venue',
        body=(
            'Training sessions are organised by CBBO/NGO partner officers and KAU. '
            'Sessions relevant to your FPO appear in the trainings area with the '
            'topic, date, venue and the conducting officer, and your FPO is notified '
            'when a session is created for it. There is no separate registration '
            'step — being listed for the session is your invitation, and attendance '
            'is recorded by the conducting officer. Past sessions, including who '
            'conducted them and attendance, are kept in the session history shown to '
            'your FPO.'
        ),
    ),
    dict(
        topic='Expert consultations — slots, status, rescheduling and what to expect',
        audiences=FPO,
        keywords='consultation slot length duration online video call link appointment status rescheduled greyed out dates calendar accept accepted declined again certificate completed expert not replying not working bok apointmnt expart book appointment',
        body=(
            'Appointment slots are defined by each expert when they set their '
            'availability — the start and end time of the slot you pick is the '
            'length of the consultation. Dates appear greyed out on the calendar '
            'when the expert has no available slots that day; pick a date that is '
            'active or check back after the expert updates availability. You can '
            'follow your request under My Bookings: it starts as Pending and the '
            'expert then Confirms or Rejects it — you are notified either way, '
            'including when a booking is declined with the expert\'s reason, and '
            'you may book a different slot and try again. The platform does not '
            'issue consultation certificates, and how the meeting happens (in '
            'person, phone or an online link) is arranged between you and the '
            'expert — use the enquiry message to agree on it. If an expert does '
            'not respond for several days, send an enquiry reminder or choose '
            'another expert in the same specialisation.'
        ),
    ),
    dict(
        topic='Interface basics — dark mode, side menu, and changing your password',
        audiences=FPO + ADMIN + GOV + CBBO,
        keywords='dark mode theme toggle light hide side menu collapse sidebar change password how to chnge pasword paswrd',
        body=(
            'Use the theme toggle in the top bar to switch between light and dark '
            'mode. The side menu can be collapsed with the menu (hamburger) control '
            'next to the logo, giving the page more width. To change your password, '
            'open Settings and use the change-password option — enter your current '
            'password and the new one (minimum 8 characters with an uppercase '
            'letter, lowercase letter, digit and special character). If you have '
            'forgotten the password, use "Forgot password" on the login screen '
            'instead.'
        ),
    ),

    # ── Super admin ─────────────────────────────────────────────────────
    dict(
        topic='Admin — finding and verifying translations',
        audiences=ADMIN,
        keywords='unverified translations find filter verify language strings review',
        body=(
            'Open Admin → Languages & Translations. The translations table can be '
            'filtered by language, category and verification status — filter by '
            'unverified to list every string still awaiting review, then open each '
            'entry and mark it verified. Export and import via Excel/CSV are '
            'available for bulk translation work.'
        ),
    ),
    dict(
        topic='Admin — scheme and training expiry windows (auto-hide)',
        audiences=ADMIN,
        keywords='scheme auto expire days after deadline training expiry window change 10 days hide old sessions sub-admin settings',
        body=(
            'Expired content is hidden automatically: a scheme is hidden N days '
            'after its deadline and a training session N days after its date. Both '
            'windows default to 5 days and are configurable in Admin → Sub-admin '
            'Settings (scheme expiry days and training expiry days) — set the '
            'training window to 10 there if you want sessions visible longer. The '
            'records are hidden, not deleted, and an admin can still see and edit '
            'them in the respective admin pages.'
        ),
    ),
    dict(
        topic='Admin — FPO action permissions (what codes like can_delete_docs mean)',
        audiences=ADMIN,
        keywords='can_delete_docs can_upload_docs can_submit can_invite_team permission codes meaning matrix fpo roles',
        body=(
            'The FPO permission matrix (Admin → FPO Permissions) controls what each '
            'FPO role may do per page. The action codes read naturally: '
            'can_view_dashboard (open the dashboard), can_submit (submit the '
            'application), can_upload_docs / can_view_docs / can_delete_docs '
            '(manage registration documents — can_delete_docs allows removing an '
            'uploaded document while the application is in draft), can_edit_profile, '
            'can_invite_team and can_manage_team (team administration), and '
            'can_submit_claim (ownership claims). Ticking or unticking a cell '
            'changes what every user holding that role can do.'
        ),
    ),
    dict(
        topic='Admin — platform counts and directories (FPOs, officials, buyers, feedback)',
        audiences=ADMIN,
        keywords='how many fpos approved district count aproved tvm government officials cbbo officers registered buyers directory organisation feedback unread resolve latest dashboard stats compare farms',
        body=(
            'Live counts are on the admin dashboard: total and district-wise '
            'approved FPOs, tier distribution and monthly trends. Directories have '
            'their own pages — Government Officials and CBBO Officers lists show '
            'every registered account with status, and the Buyers page lists '
            'registered buyers with their organisation. Website feedback arrives in '
            'Admin → Feedback, where each message can be opened and its status '
            'updated (for example marked resolved). The assistant cannot run these '
            'queries for you — the pages always have the current numbers.'
        ),
    ),
    dict(
        topic='Admin — duplicate FPO entries, ownership claims and suspension history',
        audiences=ADMIN,
        keywords='two entries duplicate fpo why claim basis who suspended history status change audit',
        body=(
            'Two FPO rows with the same name usually mean a duplicate registration '
            'attempt: the original FPO plus a blocked draft that triggered the '
            '"Claim Your Business" flow. Ownership claims are reviewed under Admin → '
            'Ownership Claims, where each claim shows the claimant\'s stated basis '
            'and supporting documents before you approve or reject. Every status '
            'change on an FPO — including suspension, with the acting admin and '
            'reason — is recorded in the application\'s status timeline (Admin → '
            'FPO Applications → the FPO → history) and in the audit trail (Admin → '
            'Audit Logs).'
        ),
    ),
    dict(
        topic='Admin — master data (commodities, promoting agencies, banks, blocks)',
        audiences=ADMIN,
        keywords='commodities configured how many sections promoting agencies list banks master data blocks categories',
        body=(
            'Dropdown values across the platform come from the master data store: '
            'commodities (grouped into sections such as crops, livestock, fisheries '
            'and value-added products), promoting agencies (NABARD, SFAC, NCDC and '
            'others), the bank list, legal structures, and district blocks. The '
            'public master-data API and the admin master data screens show the '
            'current values; new entries are added there and appear in every form '
            'immediately — no code change needed.'
        ),
    ),
    dict(
        topic='Admin — site content: logos, gallery, team members, partners and video playlists',
        audiences=ADMIN,
        keywords='header logo size configured gallery albums photos team members principal investigator committee technical consultant partners youtube playlists news sources',
        body=(
            'The public website\'s content is managed in the Admin CMS pages: '
            'header/partner logos, the photo gallery (albums and photos), the Team '
            'section (Principal Investigator, Co-Investigator, committee members, '
            'technical consultants — each with name, title, photo and display '
            'order), quick links, FAQs, announcements, and the News section\'s video '
            'playlists (each entry stores a YouTube playlist with its title and '
            'logo). Counts and current values are always visible on those pages; '
            'image uploads show the recommended dimensions beside the upload field.'
        ),
    ),
    dict(
        topic='Admin — DPR financial configuration (the platform defaults)',
        audiences=ADMIN,
        keywords='DPR discount rate NPV IRR loan interest default tenure moratorium corporate tax depreciation rates buildings machinery equipment rule engine enabled configuration',
        body=(
            'DPR calculation defaults live in Admin → DPR Configuration and are '
            'editable there: discount rate 12% (NPV/IRR), default loan terms 10.5% '
            'interest, 5-year tenure, 12-month moratorium with interest serviced '
            'during the moratorium, corporate tax 25.17%, straight-line '
            'depreciation 10% for buildings and 15% for machinery and for '
            'equipment/vehicles/utilities, projection period 10 years, and the '
            'working-capital interest rate 10.5%. The dynamic questionnaire rule '
            'engine is enabled by default and its section-applicability rules are '
            'managed in Admin → DPR Applicability — that page also shows which '
            'answers trigger which guidance tips.'
        ),
    ),
    dict(
        topic='Admin — viewing any FPO\'s full profile and DPR list',
        audiences=ADMIN,
        keywords='fpo profile details promoting agency commodities turnover members gender registered act trainings weakest domain dprs generated view',
        body=(
            'Open Admin → FPO Applications and select the FPO to see its complete '
            'profile: legal structure and registration act, promoting agency, '
            'commodities, declared annual turnover (entered in lakhs), member '
            'breakdown including gender, documents, status history and tier '
            'assessment results (including per-domain scores — the lowest domain '
            'is where the FPO is weakest). The FPO\'s DPR projects and generated '
            'documents are under Admin → DPR. The assistant answers general '
            'questions, but for a specific FPO\'s current data always use these '
            'pages — and note that draft (unsubmitted) FPOs appear only there, '
            'not in the assistant\'s knowledge.'
        ),
    ),

    # ── Government officials ────────────────────────────────────────────
    dict(
        topic='Government official registration — what happens after submitting',
        audiences=GOV + PUB,
        keywords='government official register submit form what happens pending approval approved rejected credentials jurisdiction details shown',
        body=(
            'After you submit the government-official registration form, your '
            'application goes to the KAU admin for review — it appears in their '
            'pending list with your name, designation, department, jurisdiction '
            'and contact details. On approval you are notified and your login is '
            'activated (if a temporary password is issued you must change it at '
            'first login). If the application is rejected you are notified with '
            'the reason and may correct and reapply. Temporary passwords are '
            'personal — the assistant can never reveal any account\'s password.'
        ),
    ),

    # ── CBBO officers ───────────────────────────────────────────────────
    dict(
        topic='CBBO training sessions — creating, visibility, attendance and deletion',
        audiences=CBBO + ADMIN,
        keywords='training session create fpo notified delete visibility other officers attendance mark conducted this month organisation dropdown empty add organisation',
        body=(
            'When you create a training session and list FPOs for it, those FPOs '
            'are notified. You see and manage the sessions you created; sessions '
            'by other officers are not in your working list — ask the admin for a '
            'cross-officer view. Attendance is recorded on the session after it '
            'takes place, and your conducted-session history (with counts) is on '
            'your sessions page. Deleting a session removes it from the FPOs\' '
            'training lists as well, so prefer editing over deleting once FPOs '
            'are notified. The organisation dropdown at registration is '
            'admin-managed — if your organisation is missing, contact the KAU '
            'admin to have it added; you cannot add one yourself.'
        ),
    ),
    dict(
        topic='CBBO marketplace view — why sold and expired batches are visible',
        audiences=CBBO + GOV + ADMIN,
        keywords='sold expired batches visible marketplace stock history why see',
        body=(
            'Partner-facing views of FPO products intentionally include sold and '
            'expired stock batches — the history shows an FPO\'s real market '
            'activity, which matters for capacity-building assessment, not just '
            'what is currently on sale. Buyers, by contrast, see only live '
            'sellable stock.'
        ),
    ),
]


def seed_chatbot_kb_gap_fill():
    from apps.database.models import ChatKnowledgeEntry
    created = updated = 0
    for i, e in enumerate(ENTRIES):
        _, was_new = ChatKnowledgeEntry.objects.update_or_create(
            topic=e['topic'],
            defaults={
                'body_en':       e['body'],
                'keywords':      e['keywords'],
                'audiences':     e['audiences'],
                'pages':         e.get('pages', []),
                'is_active':     True,
                'display_order': 500 + i,
            },
        )
        created += was_new
        updated += (not was_new)
    print(f'Chatbot KB gap-fill: {created} created, {updated} updated '
          f'({len(ENTRIES)} entries).')
