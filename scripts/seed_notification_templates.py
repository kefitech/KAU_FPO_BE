"""
Seed notification template codes and templates.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_notification_templates.py').read())
    seed_notification_templates()
    "

Idempotent — skips existing entries.
Add new template codes here as new features are built.
"""

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

from apps.database.models import NotificationTemplateCode, NotificationTemplate, Language


TEMPLATE_CODES = [
    # code                    | channel     | description                                    | variables
    ('welcome',               'email',      'Welcome email with login credentials',          ['user_name', 'email', 'temp_password']),
    ('welcome',               'sms',        'Welcome SMS with login credentials',            ['user_name', 'temp_password']),
    ('welcome',               'whatsapp',   'Welcome WhatsApp with login credentials',       ['user_name', 'temp_password']),
    ('welcome_fpo',           'email',      'Welcome email for self-registered FPO users (no credentials block)', ['user_name']),
    ('welcome_fpo',           'sms',        'Welcome SMS for self-registered FPO users',     ['user_name']),
    ('email_verification',    'email',      'OTP for email verification at registration',    ['user_name', 'otp']),
    ('mobile_verification',   'sms',        'OTP for phone verification and password reset', ['otp']),
    ('application_submitted', 'email',      'FPO application submitted confirmation',        ['user_name', 'application_id']),
    ('application_submitted', 'sms',        'FPO application submitted SMS confirmation',    ['user_name', 'application_id']),
    ('application_approved',  'email',      'FPO application approved notification',         ['user_name', 'fpo_name', 'application_id']),
    ('application_approved',  'sms',        'FPO application approved SMS',                  ['user_name', 'application_id']),
    ('application_approved',  'whatsapp',   'FPO application approved WhatsApp',             ['user_name', 'application_id']),
    ('application_rejected',  'email',      'FPO application rejected notification',         ['user_name', 'fpo_name', 'rejection_reason']),
    ('application_rejected',  'whatsapp',   'FPO application rejected WhatsApp',             ['user_name', 'rejection_reason']),
    ('info_requested',        'email',      'Additional information requested from FPO',     ['user_name', 'request_message']),
    ('password_reset',        'email',      'Password reset link email',                     ['user_name', 'reset_link']),
    ('password_changed',      'email',      'Password changed confirmation email',           ['user_name']),
    ('two_factor_otp',              'email', 'OTP email for 2FA recovery (disable 2FA)',          ['user_name', 'otp']),
    ('fpo_email_otp',               'email', 'OTP to verify FPO office email before submission',   ['user_name', 'otp']),
    ('fpo_phone_otp',               'sms',   'OTP to verify FPO office phone before submission',   ['otp']),
    ('admin_new_fpo_application',   'email',  'Notify admin when a new FPO application is submitted', ['fpo_name', 'application_id', 'district']),
    ('application_approved',        'in_app', 'In-app notification when FPO is approved',             ['user_name', 'application_id']),
    ('application_rejected',        'in_app', 'In-app notification when FPO is rejected',             ['user_name', 'rejection_reason']),
    ('info_requested',              'in_app', 'In-app notification when admin requests more info',     ['user_name', 'request_message']),
    # Ownership claim workflow
    ('claim_submitted',             'email',  'Notify claimant that claim is received and under review', ['user_name', 'fpo_name']),
    ('claim_submitted',             'in_app', 'In-app: claim received confirmation',                     ['user_name', 'fpo_name']),
    ('claim_approved',              'email',  'Notify claimant that their ownership claim was approved',  ['user_name', 'fpo_name']),
    ('claim_approved',              'in_app', 'In-app: claim approved confirmation',                      ['user_name', 'fpo_name']),
    ('claim_rejected',              'email',  'Notify claimant that their ownership claim was rejected',  ['user_name', 'fpo_name', 'rejection_reason']),
    ('claim_rejected',              'in_app', 'In-app: claim rejected notification',                      ['user_name', 'fpo_name', 'rejection_reason']),
    ('claim_ownership_revoked',     'email',  'Notify old primary/secondary users that FPO access was revoked after claim approval', ['user_name', 'fpo_name']),
    ('claim_ownership_revoked',     'in_app', 'In-app: FPO access revoked due to ownership transfer',    ['user_name', 'fpo_name']),
    ('claim_draft_removed',         'email',  'Notify claimant that their incomplete draft FPO was removed during ownership transfer', ['user_name', 'fpo_name']),
    ('claim_draft_removed',         'in_app', 'In-app: draft FPO removed during ownership transfer',     ['user_name', 'fpo_name']),
    ('claim_new_admin',             'in_app', 'Notify admin inbox when a new ownership claim is submitted', ['fpo_name', 'claimant_name']),
    ('claim_docs_requested',        'email',  'Notify claimant that admin is requesting additional documents', ['user_name', 'fpo_name', 'admin_message']),
    ('claim_docs_requested',        'sms',    'SMS to claimant: admin requesting additional documents',        ['user_name', 'fpo_name']),
    ('claim_docs_requested',        'in_app', 'In-app: admin requesting additional documents for claim',       ['user_name', 'fpo_name', 'admin_message']),
]


# Templates: (code, channel, language_code, subject, body)
TEMPLATES = [
    (
        'mobile_verification', 'sms', 'en', '',
        'Your KAU-FPO OTP is {{otp}}. Valid for 10 minutes. Do not share with anyone.',
    ),
    (
        'mobile_verification', 'sms', 'ml', '',
        'നിങ്ങളുടെ KAU-FPO OTP ആണ് {{otp}}. 10 മിനിറ്റ് സാധുവാണ്. ആരുമായും പങ്കിടരുത്.',
    ),
    (
        'password_reset', 'email', 'en',
        'Reset Your KAU-FPO Password',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We received a request to reset your KAU-FPO account password.</p>'
            '<p>Click the button below to set a new password. This link is valid for <strong>15 minutes</strong>.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">If you did not request a password reset, you can safely ignore this email.</p>'
        ),
    ),
    (
        'password_reset', 'email', 'ml',
        'നിങ്ങളുടെ KAU-FPO പാസ്‌വേഡ് റീസെറ്റ് ചെയ്യുക',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>നിങ്ങളുടെ KAU-FPO അക്കൗണ്ടിന്റെ പാസ്‌വേഡ് റീസെറ്റ് ചെയ്യാൻ ഒരു അഭ്യർത്ഥന ലഭിച്ചു.</p>'
            '<p>പുതിയ പാസ്‌വേഡ് സജ്ജമാക്കാൻ ചുവടെയുള്ള ബട്ടൺ ക്ലിക്ക് ചെയ്യുക. ഈ ലിങ്ക് <strong>15 മിനിറ്റ്</strong> സാധുവാണ്.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">നിങ്ങൾ ഇത് അഭ്യർത്ഥിച്ചില്ലെങ്കിൽ ഈ ഇമെയിൽ അവഗണിക്കുക.</p>'
        ),
    ),
    (
        'password_changed', 'email', 'en',
        'Your KAU-FPO Password Has Been Changed',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Your KAU-FPO account password has been successfully changed.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">'
            'If you did not make this change, please contact support immediately.'
            '</p>'
        ),
    ),
    (
        'password_changed', 'email', 'ml',
        'നിങ്ങളുടെ KAU-FPO പാസ്‌വേഡ് മാറ്റി',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>നിങ്ങളുടെ KAU-FPO അക്കൗണ്ടിന്റെ പാസ്‌വേഡ് വിജയകരമായി മാറ്റി.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">'
            'നിങ്ങൾ ഈ മാറ്റം വരുത്തിയില്ലെങ്കിൽ, ഉടൻ സപ്പോർട്ടിനെ ബന്ധപ്പെടുക.'
            '</p>'
        ),
    ),
    (
        'welcome', 'email', 'en',
        'Your KAU-FPO Platform Account is Ready',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Welcome to the <strong>KAU-FPO Digital Platform</strong>! Your account has been created.</p>'
            '<p>Here are your login credentials:</p>'
            '<table style="margin:12px 0;border-collapse:collapse;">'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">Email</td>'
            '<td style="padding:4px 0;font-weight:600;">{{email}}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">Temporary Password</td>'
            '<td style="padding:4px 0;font-weight:600;letter-spacing:1px;">{{temp_password}}</td></tr>'
            '</table>'
            '<p style="margin-top:4px;font-size:13px;color:#888888;">Please log in and change your password immediately.</p>'
        ),
    ),
    (
        'welcome', 'email', 'ml',
        'നിങ്ങളുടെ KAU-FPO അക്കൗണ്ട് തയ്യാറാണ്',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p><strong>KAU-FPO ഡിജിറ്റൽ പ്ലാറ്റ്‌ഫോമിലേക്ക്</strong> സ്വാഗതം! നിങ്ങളുടെ അക്കൗണ്ട് തയ്യാറാക്കി.</p>'
            '<p>നിങ്ങളുടെ ലോഗിൻ വിവരങ്ങൾ:</p>'
            '<table style="margin:12px 0;border-collapse:collapse;">'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">ഇമെയിൽ</td>'
            '<td style="padding:4px 0;font-weight:600;">{{email}}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">താൽക്കാലിക പാസ്‌വേഡ്</td>'
            '<td style="padding:4px 0;font-weight:600;letter-spacing:1px;">{{temp_password}}</td></tr>'
            '</table>'
            '<p style="margin-top:4px;font-size:13px;color:#888888;">ദയവായി ലോഗിൻ ചെയ്ത് ഉടൻ പാസ്‌വേഡ് മാറ്റുക.</p>'
        ),
    ),
    (
        'welcome', 'sms', 'en', '',
        'Welcome to KAU-FPO, {{user_name}}! Your temporary password is {{temp_password}}. Login and change it immediately.',
    ),
    (
        'welcome', 'sms', 'ml', '',
        'KAU-FPO-ലേക്ക് സ്വാഗതം, {{user_name}}! നിങ്ങളുടെ താൽക്കാലിക പാസ്‌വേഡ്: {{temp_password}}. ഉടൻ ലോഗിൻ ചെയ്ത് മാറ്റുക.',
    ),
    (
        'welcome_fpo', 'email', 'en',
        'Welcome to KAU-FPO Digital Platform',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Welcome to the <strong>KAU-FPO Digital Platform</strong>! Your account has been created successfully.</p>'
            '<p>You can now log in and begin your FPO registration. Our platform will guide you through each step of the process.</p>'
            '<p style="margin-top:8px;font-size:13px;color:#888888;">If you have any questions, please contact our support team.</p>'
        ),
    ),
    (
        'welcome_fpo', 'email', 'ml',
        'KAU-FPO ഡിജിറ്റൽ പ്ലാറ്റ്‌ഫോമിലേക്ക് സ്വാഗതം',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p><strong>KAU-FPO ഡിജിറ്റൽ പ്ലാറ്റ്‌ഫോമിലേക്ക്</strong> സ്വാഗതം! നിങ്ങളുടെ അക്കൗണ്ട് വിജയകരമായി സൃഷ്ടിച്ചു.</p>'
            '<p>ഇപ്പോൾ ലോഗിൻ ചെയ്ത് നിങ്ങളുടെ FPO രജിസ്‌ട്രേഷൻ ആരംഭിക്കാം. ഓരോ ഘട്ടത്തിലും പ്ലാറ്റ്‌ഫോം നിങ്ങളെ നയിക്കും.</p>'
        ),
    ),
    (
        'welcome_fpo', 'sms', 'en', '',
        'Welcome to KAU-FPO Platform, {{user_name}}! Your account is ready. Log in to start your FPO registration.',
    ),
    (
        'welcome_fpo', 'sms', 'ml', '',
        'KAU-FPO പ്ലാറ്റ്‌ഫോമിലേക്ക് സ്വാഗതം, {{user_name}}! നിങ്ങളുടെ അക്കൗണ്ട് തയ്യാറാണ്. FPO രജിസ്‌ട്രേഷൻ ആരംഭിക്കാൻ ലോഗിൻ ചെയ്യുക.',
    ),
    (
        'application_submitted', 'email', 'en',
        'FPO Application Submitted — {{application_id}}',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Your FPO application has been submitted successfully.</p>'
            '<p style="margin:12px 0;">'
            '<span style="color:#666;font-size:13px;">Application ID</span><br>'
            '<strong style="font-size:16px;letter-spacing:0.5px;">{{application_id}}</strong>'
            '</p>'
            '<p>Our team will review your application and get back to you shortly.</p>'
        ),
    ),
    (
        'application_approved', 'email', 'en',
        'Congratulations! Your FPO Application is Approved',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We are pleased to inform you that your FPO application for '
            '<strong>{{fpo_name}}</strong> (ID: {{application_id}}) has been <strong style="color:#2e7d32;">approved</strong>.</p>'
            '<p>You can now access all platform features. Log in to get started.</p>'
        ),
    ),
    (
        'application_rejected', 'email', 'en',
        'FPO Application Update — Action Required',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We regret to inform you that your FPO application for <strong>{{fpo_name}}</strong> '
            'has not been approved at this time.</p>'
            '<p><strong>Reason:</strong></p>'
            '<p style="background:#fff8f8;border-left:3px solid #e53935;padding:10px 14px;color:#555;font-size:14px;">{{rejection_reason}}</p>'
            '<p>You may correct the issues and resubmit your application.</p>'
        ),
    ),
    (
        'info_requested', 'email', 'en',
        'Additional Information Required for Your FPO Application',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Our team requires additional information to process your application.</p>'
            '<p style="background:#f5f5f5;border-left:3px solid #2e7d32;padding:10px 14px;color:#555;font-size:14px;">{{request_message}}</p>'
            '<p>Please log in and update your application at the earliest.</p>'
        ),
    ),
    (
        'two_factor_otp', 'email', 'en',
        'Your KAU-FPO 2FA Recovery OTP',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>You requested to disable Two-Factor Authentication on your KAU-FPO account.</p>'
            '<p>Your recovery OTP is:</p>'
            '<p style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;'
            'padding:16px;background:#f5f5f5;border-radius:4px;color:#2e7d32;">{{otp}}</p>'
            '<p>This OTP is valid for <strong>10 minutes</strong>. Do not share it with anyone.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">'
            'If you did not request this, your account may be at risk. '
            'Please contact support immediately.'
            '</p>'
        ),
    ),
    (
        'two_factor_otp', 'email', 'ml',
        'നിങ്ങളുടെ KAU-FPO 2FA റിക്കവറി OTP',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>നിങ്ങളുടെ KAU-FPO അക്കൗണ്ടിൽ Two-Factor Authentication നിർത്തലാക്കാൻ '
            'ഒരു അഭ്യർത്ഥന ലഭിച്ചു.</p>'
            '<p>നിങ്ങളുടെ റിക്കവറി OTP:</p>'
            '<p style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;'
            'padding:16px;background:#f5f5f5;border-radius:4px;color:#2e7d32;">{{otp}}</p>'
            '<p>ഈ OTP <strong>10 മിനിറ്റ്</strong> സാധുവാണ്. ആരുമായും പങ്കിടരുത്.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">'
            'നിങ്ങൾ ഇത് അഭ്യർത്ഥിച്ചില്ലെങ്കിൽ, ഉടൻ സപ്പോർട്ടിനെ ബന്ധപ്പെടുക.'
            '</p>'
        ),
    ),
    # ── FPO verification OTPs ────────────────────────────────────────────────────
    (
        'fpo_email_otp', 'email', 'en',
        'Verify Your FPO Office Email — KAU-FPO',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Please use the OTP below to verify your FPO office email address.</p>'
            '<p style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;'
            'padding:16px;background:#f5f5f5;border-radius:4px;color:#2e7d32;">{{otp}}</p>'
            '<p>This OTP is valid for <strong>10 minutes</strong>. Do not share it with anyone.</p>'
        ),
    ),
    (
        'fpo_email_otp', 'email', 'ml',
        'നിങ്ങളുടെ FPO ഓഫീസ് ഇമെയിൽ സ്ഥിരീകരിക്കുക — KAU-FPO',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>നിങ്ങളുടെ FPO ഓഫീസ് ഇമെയിൽ സ്ഥിരീകരിക്കാൻ ചുവടെയുള്ള OTP ഉപയോഗിക്കുക.</p>'
            '<p style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;'
            'padding:16px;background:#f5f5f5;border-radius:4px;color:#2e7d32;">{{otp}}</p>'
            '<p>ഈ OTP <strong>10 മിനിറ്റ്</strong> സാധുവാണ്. ആരുമായും പങ്കിടരുത്.</p>'
        ),
    ),
    (
        'fpo_phone_otp', 'sms', 'en', '',
        'Your KAU-FPO phone verification OTP is {{otp}}. Valid for 10 minutes. Do not share with anyone.',
    ),
    (
        'fpo_phone_otp', 'sms', 'ml', '',
        'നിങ്ങളുടെ KAU-FPO ഫോൺ സ്ഥിരീകരണ OTP ആണ് {{otp}}. 10 മിനിറ്റ് സാധുവാണ്. ആരുമായും പങ്കിടരുത്.',
    ),
    (
        'admin_new_fpo_application', 'email', 'en',
        'New FPO Application Submitted — {{application_id}}',
        (
            '<p>A new FPO application has been submitted and is awaiting review.</p>'
            '<table style="margin:12px 0;border-collapse:collapse;">'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">FPO Name</td>'
            '<td style="padding:4px 0;font-weight:600;">{{fpo_name}}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">Application ID</td>'
            '<td style="padding:4px 0;font-weight:600;letter-spacing:0.5px;">{{application_id}}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">District</td>'
            '<td style="padding:4px 0;">{{district}}</td></tr>'
            '</table>'
            '<p>Please log in to the admin panel to review this application.</p>'
        ),
    ),
    # ── WhatsApp templates ───────────────────────────────────────────────────────
    # whatsapp_template_name must match the Meta-approved template name exactly.
    # These are placeholder names — KAU updates them after Meta approval via the API.
    (
        'welcome', 'whatsapp', 'en', '',
        'Welcome to KAU-FPO, {{user_name}}! Your temporary password is {{temp_password}}. Login and change it immediately.',
        {'whatsapp_template_name': 'kau_fpo_welcome', 'whatsapp_template_language': 'en'},
    ),
    (
        'welcome', 'whatsapp', 'ml', '',
        'KAU-FPO-ലേക്ക് സ്വാഗതം, {{user_name}}! നിങ്ങളുടെ താൽക്കാലിക പാസ്‌വേഡ്: {{temp_password}}. ഉടൻ ലോഗിൻ ചെയ്ത് മാറ്റുക.',
        {'whatsapp_template_name': 'kau_fpo_welcome', 'whatsapp_template_language': 'ml'},
    ),
    (
        'application_approved', 'whatsapp', 'en', '',
        'Congratulations {{user_name}}! Your FPO application (ID: {{application_id}}) has been approved on the KAU-FPO platform.',
        {'whatsapp_template_name': 'kau_fpo_application_approved', 'whatsapp_template_language': 'en'},
    ),
    (
        'application_approved', 'whatsapp', 'ml', '',
        'അഭിനന്ദനങ്ങൾ {{user_name}}! നിങ്ങളുടെ FPO അപ്ലിക്കേഷൻ (ID: {{application_id}}) KAU-FPO പ്ലാറ്റ്‌ഫോമിൽ അംഗീകരിച്ചു.',
        {'whatsapp_template_name': 'kau_fpo_application_approved', 'whatsapp_template_language': 'ml'},
    ),
    (
        'application_rejected', 'whatsapp', 'en', '',
        'Dear {{user_name}}, your FPO application was not approved. Reason: {{rejection_reason}}. Please log in for details.',
        {'whatsapp_template_name': 'kau_fpo_application_rejected', 'whatsapp_template_language': 'en'},
    ),
    (
        'application_rejected', 'whatsapp', 'ml', '',
        'പ്രിയ {{user_name}}, നിങ്ങളുടെ FPO അപ്ലിക്കേഷൻ അംഗീകരിച്ചില്ല. കാരണം: {{rejection_reason}}. വിശദാംശങ്ങൾക്ക് ലോഗിൻ ചെയ്യുക.',
        {'whatsapp_template_name': 'kau_fpo_application_rejected', 'whatsapp_template_language': 'ml'},
    ),
    # ── In-App Notifications ─────────────────────────────────────────────────────
    (
        'application_approved', 'in_app', 'en',
        'Your FPO Application is Approved',
        'Congratulations {{user_name}}! Your FPO application (ID: {{application_id}}) has been approved. You can now access all platform features.',
    ),
    (
        'application_approved', 'in_app', 'ml',
        'നിങ്ങളുടെ FPO അപേക്ഷ അംഗീകരിച്ചു',
        'അഭിനന്ദനങ്ങൾ {{user_name}}! നിങ്ങളുടെ FPO അപേക്ഷ (ID: {{application_id}}) അംഗീകരിച്ചു. ഇനി പ്ലാറ്റ്‌ഫോമിന്റെ എല്ലാ സൗകര്യങ്ങളും ഉപയോഗിക്കാം.',
    ),
    (
        'application_rejected', 'in_app', 'en',
        'FPO Application Not Approved',
        'Dear {{user_name}}, your FPO application was not approved. Reason: {{rejection_reason}}. Please log in to review and resubmit.',
    ),
    (
        'application_rejected', 'in_app', 'ml',
        'FPO അപേക്ഷ അംഗീകരിച്ചില്ല',
        'പ്രിയ {{user_name}}, നിങ്ങളുടെ FPO അപേക്ഷ അംഗീകരിച്ചില്ല. കാരണം: {{rejection_reason}}. ദയവായി ലോഗിൻ ചെയ്ത് വിശദാംശങ്ങൾ പരിശോധിക്കുക.',
    ),
    (
        'info_requested', 'in_app', 'en',
        'Additional Information Required',
        'Dear {{user_name}}, our team requires additional information to process your FPO application. Please log in and update your application.',
    ),
    (
        'info_requested', 'in_app', 'ml',
        'കൂടുതൽ വിവരങ്ങൾ ആവശ്യമാണ്',
        'പ്രിയ {{user_name}}, നിങ്ങളുടെ FPO അപേക്ഷ പ്രോസസ്സ് ചെയ്യാൻ കൂടുതൽ വിവരങ്ങൾ ആവശ്യമാണ്. ദയവായി ലോഗിൻ ചെയ്ത് അപ്ഡേറ്റ് ചെയ്യുക.',
    ),

    # ── Ownership Claim Notifications ────────────────────────────────────────
    (
        'claim_submitted', 'email', 'en',
        'Your Ownership Claim Has Been Received',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We have received your ownership claim for <strong>{{fpo_name}}</strong>.</p>'
            '<p>Our team will review your claim and supporting documents. You will be notified once a decision is made.</p>'
            '<p>This process typically takes 3–5 business days.</p>'
        ),
    ),
    (
        'claim_submitted', 'email', 'ml',
        'നിങ്ങളുടെ ഉടമസ്ഥാവകാശ അവകാശവാദം ലഭിച്ചു',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p><strong>{{fpo_name}}</strong>-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം ലഭിച്ചു.</p>'
            '<p>ഞങ്ങളുടെ ടീം നിങ്ങളുടെ അവകാശവാദം അവലോകനം ചെയ്യും. തീരുമാനം ആകുമ്പോൾ അറിയിക്കും.</p>'
        ),
    ),
    (
        'claim_submitted', 'in_app', 'en',
        'Ownership Claim Submitted',
        'Dear {{user_name}}, your ownership claim for {{fpo_name}} has been received and is under review.',
    ),
    (
        'claim_submitted', 'in_app', 'ml',
        'ഉടമസ്ഥാവകാശ അവകാശവാദം സമർപ്പിച്ചു',
        'പ്രിയ {{user_name}}, {{fpo_name}}-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം ലഭിച്ചു. അവലോകനം ചെയ്തുകൊണ്ടിരിക്കുന്നു.',
    ),
    (
        'claim_approved', 'email', 'en',
        'Your Ownership Claim Has Been Approved',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>Congratulations! Your ownership claim for <strong>{{fpo_name}}</strong> has been <strong>approved</strong>.</p>'
            '<p>You are now the primary user of this FPO. Please log in to complete your profile and access all platform features.</p>'
        ),
    ),
    (
        'claim_approved', 'email', 'ml',
        'നിങ്ങളുടെ ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചു',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>അഭിനന്ദനങ്ങൾ! <strong>{{fpo_name}}</strong>-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം <strong>അംഗീകരിച്ചു</strong>.</p>'
            '<p>ഇപ്പോൾ നിങ്ങൾ ഈ FPO-യുടെ പ്രാഥമിക ഉപയോക്താവാണ്. ദയവായി ലോഗിൻ ചെയ്ത് പ്രൊഫൈൽ പൂർത്തിയാക്കുക.</p>'
        ),
    ),
    (
        'claim_approved', 'in_app', 'en',
        'Ownership Claim Approved',
        'Congratulations {{user_name}}! Your ownership claim for {{fpo_name}} has been approved. You are now the primary user.',
    ),
    (
        'claim_approved', 'in_app', 'ml',
        'ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചു',
        'അഭിനന്ദനങ്ങൾ {{user_name}}! {{fpo_name}}-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചു. നിങ്ങൾ ഇപ്പോൾ പ്രാഥമിക ഉപയോക്താവാണ്.',
    ),
    (
        'claim_rejected', 'email', 'en',
        'Your Ownership Claim Was Not Approved',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We regret to inform you that your ownership claim for <strong>{{fpo_name}}</strong> has been <strong>rejected</strong>.</p>'
            '<p><strong>Reason:</strong> {{rejection_reason}}</p>'
            '<p>If you believe this is an error, please contact KAU support for further assistance.</p>'
        ),
    ),
    (
        'claim_rejected', 'email', 'ml',
        'നിങ്ങളുടെ ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചില്ല',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p><strong>{{fpo_name}}</strong>-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം <strong>നിരസിച്ചു</strong>.</p>'
            '<p><strong>കാരണം:</strong> {{rejection_reason}}</p>'
            '<p>ഇത് തെറ്റാണെന്ന് കരുതുന്നെങ്കിൽ KAU സഹായ കേന്ദ്രവുമായി ബന്ധപ്പെടുക.</p>'
        ),
    ),
    (
        'claim_rejected', 'in_app', 'en',
        'Ownership Claim Rejected',
        'Dear {{user_name}}, your ownership claim for {{fpo_name}} was not approved. Reason: {{rejection_reason}}.',
    ),
    (
        'claim_rejected', 'in_app', 'ml',
        'ഉടമസ്ഥാവകാശ അവകാശവാദം നിരസിച്ചു',
        'പ്രിയ {{user_name}}, {{fpo_name}}-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചില്ല. കാരണം: {{rejection_reason}}.',
    ),
    (
        'claim_ownership_revoked', 'email', 'en',
        'Your FPO Access Has Been Revoked',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>This is to inform you that your access to <strong>{{fpo_name}}</strong> on the KAU-FPO platform has been revoked.</p>'
            '<p>This action was taken following the approval of an ownership claim by the rightful owner of this FPO.</p>'
            '<p>If you believe this is an error, please contact KAU support immediately.</p>'
        ),
    ),
    (
        'claim_ownership_revoked', 'email', 'ml',
        'നിങ്ങളുടെ FPO ആക്‌സസ് റദ്ദാക്കി',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p>KAU-FPO പ്ലാറ്റ്‌ഫോമിൽ <strong>{{fpo_name}}</strong>-ലേക്കുള്ള നിങ്ങളുടെ ആക്‌സസ് റദ്ദാക്കിയിരിക്കുന്നു.</p>'
            '<p>ഈ FPO-യുടെ ഉടമസ്ഥാവകാശ അവകാശവാദം അംഗീകരിച്ചതിനാൽ ഈ നടപടി സ്വീകരിച്ചു.</p>'
            '<p>ഇത് തെറ്റാണെന്ന് കരുതുന്നെങ്കിൽ ഉടൻ KAU സഹായ കേന്ദ്രവുമായി ബന്ധപ്പെടുക.</p>'
        ),
    ),
    (
        'claim_ownership_revoked', 'in_app', 'en',
        'FPO Access Revoked',
        'Dear {{user_name}}, your access to {{fpo_name}} has been revoked following an ownership transfer approved by KAU Admin.',
    ),
    (
        'claim_ownership_revoked', 'in_app', 'ml',
        'FPO ആക്‌സസ് റദ്ദാക്കി',
        'പ്രിയ {{user_name}}, KAU അഡ്‌മിൻ അംഗീകരിച്ച ഉടമസ്ഥ കൈമാറ്റത്തെ തുടർന്ന് {{fpo_name}}-ലേക്കുള്ള നിങ്ങളുടെ ആക്‌സസ് റദ്ദാക്കി.',
    ),
    (
        'claim_draft_removed', 'email', 'en',
        'Your Draft FPO Registration Has Been Removed',
        '<p>Dear <strong>{{user_name}}</strong>,</p>'
        '<p>As part of approving your ownership claim for <strong>{{fpo_name}}</strong>, '
        'your incomplete draft FPO registration has been automatically removed.</p>'
        '<p>You are now the primary owner of <strong>{{fpo_name}}</strong>. '
        'Please log in to access your FPO dashboard.</p>',
    ),
    (
        'claim_draft_removed', 'email', 'ml',
        'നിങ്ങളുടെ ഡ്രാഫ്റ്റ് FPO രജിസ്ട്രേഷൻ നീക്കം ചെയ്തു',
        '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
        '<p><strong>{{fpo_name}}</strong>-ന്റെ ഉടമസ്ഥ അവകാശം അംഗീകരിക്കുന്നതിന്റെ ഭാഗമായി, '
        'നിങ്ങളുടെ അപൂർണ്ണ ഡ്രാഫ്റ്റ് FPO രജിസ്ട്രേഷൻ സ്വയമേവ നീക്കം ചെയ്തിരിക്കുന്നു.</p>'
        '<p>നിങ്ങൾ ഇപ്പോൾ <strong>{{fpo_name}}</strong>-ന്റെ പ്രാഥമിക ഉടമസ്ഥനാണ്.</p>',
    ),
    (
        'claim_draft_removed', 'in_app', 'en',
        'Draft FPO Registration Removed',
        'Dear {{user_name}}, your incomplete draft FPO registration was removed as part of the ownership transfer approval for {{fpo_name}}. You are now the primary owner.',
    ),
    (
        'claim_draft_removed', 'in_app', 'ml',
        'ഡ്രാഫ്റ്റ് FPO രജിസ്ട്രേഷൻ നീക്കം ചെയ്തു',
        'പ്രിയ {{user_name}}, {{fpo_name}}-ന്റെ ഉടമസ്ഥ കൈമാറ്റ അംഗീകാരത്തിന്റെ ഭാഗമായി നിങ്ങളുടെ ഡ്രാഫ്റ്റ് FPO രജിസ്ട്രേഷൻ നീക്കം ചെയ്തു. നിങ്ങൾ ഇപ്പോൾ പ്രാഥമിക ഉടമസ്ഥനാണ്.',
    ),
    (
        'claim_new_admin', 'in_app', 'en',
        'New Ownership Claim Received',
        'A new ownership claim has been submitted for <strong>{{fpo_name}}</strong> by {{claimant_name}}. Please review and take action.',
    ),
    (
        'claim_new_admin', 'in_app', 'ml',
        'പുതിയ ഉടമസ്ഥാവകാശ അവകാശവാദം ലഭിച്ചു',
        '{{claimant_name}} {{fpo_name}}-നായി ഒരു ഉടമസ്ഥാവകാശ അവകാശവാദം സമർപ്പിച്ചിരിക്കുന്നു. ദയവായി അവലോകനം ചെയ്ത് നടപടി സ്വീകരിക്കുക.',
    ),
    # Documents requested from claimant
    (
        'claim_docs_requested', 'email', 'en',
        'Additional Documents Required for Your Ownership Claim',
        (
            '<p>Dear <strong>{{user_name}}</strong>,</p>'
            '<p>We have reviewed your ownership claim for <strong>{{fpo_name}}</strong> and require additional documents before we can proceed.</p>'
            '<p><strong>Message from KAU Admin:</strong></p>'
            '<blockquote style="border-left:3px solid #2e7d32;padding-left:12px;margin:12px 0;color:#444;">{{admin_message}}</blockquote>'
            '<p>Please log in to the KAU-FPO platform and upload the requested documents at the earliest.</p>'
            '<p style="margin-top:16px;font-size:13px;color:#888888;">If you have any questions, please contact KAU support.</p>'
        ),
    ),
    (
        'claim_docs_requested', 'email', 'ml',
        'നിങ്ങളുടെ ഉടമസ്ഥാവകാശ അവകാശവാദത്തിന് അധിക രേഖകൾ ആവശ്യമാണ്',
        (
            '<p>പ്രിയ <strong>{{user_name}}</strong>,</p>'
            '<p><strong>{{fpo_name}}</strong>-ന്റെ ഉടമസ്ഥാവകാശ അവകാശവാദം അവലോകനം ചെയ്തു. തുടർനടപടിക്ക് അധിക രേഖകൾ ആവശ്യമാണ്.</p>'
            '<p><strong>KAU അഡ്‌മിൻ സന്ദേശം:</strong></p>'
            '<blockquote style="border-left:3px solid #2e7d32;padding-left:12px;margin:12px 0;color:#444;">{{admin_message}}</blockquote>'
            '<p>ദയവായി KAU-FPO പ്ലാറ്റ്‌ഫോമിൽ ലോഗിൻ ചെയ്ത് ആവശ്യമായ രേഖകൾ അപ്‌ലോഡ് ചെയ്യുക.</p>'
        ),
    ),
    (
        'claim_docs_requested', 'sms', 'en', '',
        'KAU-FPO: Additional documents required for your ownership claim of {{fpo_name}}. Please log in to upload them.',
    ),
    (
        'claim_docs_requested', 'sms', 'ml', '',
        'KAU-FPO: {{fpo_name}}-ന്റെ ഉടമസ്ഥ അവകാശവാദത്തിന് അധിക രേഖകൾ ആവശ്യമാണ്. ദയവായി ലോഗിൻ ചെയ്ത് അപ്‌ലോഡ് ചെയ്യുക.',
    ),
    (
        'claim_docs_requested', 'in_app', 'en',
        'Documents Requested for Your Ownership Claim',
        'Dear {{user_name}}, KAU Admin has requested additional documents for your ownership claim on {{fpo_name}}. Message: {{admin_message}}',
    ),
    (
        'claim_docs_requested', 'in_app', 'ml',
        'ഉടമസ്ഥ അവകാശവാദത്തിന് രേഖകൾ ആവശ്യപ്പെട്ടു',
        'പ്രിയ {{user_name}}, {{fpo_name}}-ന്റെ ഉടമസ്ഥ അവകാശവാദത്തിന് KAU അഡ്‌മിൻ അധിക രേഖകൾ ആവശ്യപ്പെട്ടിരിക്കുന്നു. സന്ദേശം: {{admin_message}}',
    ),
]


def seed_notification_templates():
    print("=" * 60)
    print("SEEDING NOTIFICATION TEMPLATE CODES & TEMPLATES")
    print("=" * 60)

    created_codes = 0
    skipped_codes = 0

    code_map = {}  # (code, channel) -> NotificationTemplateCode instance

    for code, channel, description, variables in TEMPLATE_CODES:
        obj, created = NotificationTemplateCode.objects.get_or_create(
            code=code,
            channel=channel,
            defaults={
                'description': description,
                'variables':   variables,
                'is_active':   True,
            }
        )
        code_map[(code, channel)] = obj
        if created:
            print(f"  [+] Template code: {code} ({channel})")
            created_codes += 1
        else:
            skipped_codes += 1

    print(f"\n  Template codes: {created_codes} created, {skipped_codes} skipped")

    created_templates = 0
    skipped_templates = 0

    for row in TEMPLATES:
        code, channel, lang_code, subject, body = row[:5]
        extra = row[5] if len(row) > 5 else {}

        template_code = code_map.get((code, channel))
        if not template_code:
            print(f"  [!] Template code not found for {code}/{channel} — skipping template")
            continue

        try:
            language = Language.objects.get(code=lang_code)
        except Language.DoesNotExist:
            print(f"  [!] Language '{lang_code}' not found — skipping template for {code}/{channel}")
            continue

        defaults = {
            'subject':   subject,
            'body':      body,
            'is_active': True,
            **extra,
        }

        obj, created = NotificationTemplate.objects.update_or_create(
            template_code=template_code,
            language=language,
            defaults=defaults,
        )
        if created:
            print(f"  [+] Template: {code} ({channel}/{lang_code})")
            created_templates += 1
        else:
            print(f"  [~] Updated : {code} ({channel}/{lang_code})")
            skipped_templates += 1

    print(f"  Templates      : {created_templates} created, {skipped_templates} skipped")

    # ── Seed in_app channel settings ─────────────────────────────────────────
    from apps.database.models.notification import NotificationChannelSettings
    ch, created = NotificationChannelSettings.objects.get_or_create(
        channel='in_app',
        defaults={'config': {}, 'is_active': True},
    )
    if created:
        print("\n  [+] Channel settings: in_app (no config required)")
    else:
        print("\n  [~] Channel settings: in_app already exists")

    print("\nDone.")
