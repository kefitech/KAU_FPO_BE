Here's the full list of all API endpoints currently wired up to the backend:

Auth (/api/auth/)
Method	Endpoint	Used for
POST	/auth/login/	Login
POST	/auth/logout/	Logout
GET	/auth/me/	Get user + sidebar menu
POST	/auth/password/forgot/	Forgot password
POST	/auth/password/verify-otp/	Verify OTP
POST	/auth/password/reset/	Reset password
POST	/auth/password/change/	Change temporary password (new)
Two-Factor Auth (/api/auth/2fa/)
Method	Endpoint	Used for
GET	/auth/2fa/status/	Check 2FA enabled status
POST	/auth/2fa/setup/	Start 2FA setup
POST	/auth/2fa/verify-setup/	Confirm setup with code
POST	/auth/2fa/login/verify/	Login with TOTP code
POST	/auth/2fa/login/backup/	Login with backup code
POST	/auth/2fa/regenerate-backup-codes/	Regenerate backup codes
POST	/auth/2fa/disable/{id}/	Disable 2FA
Roles (/api/auth/roles/)
Method	Endpoint
GET	/auth/roles/
GET	/auth/roles/{id}/
POST	/auth/roles/
PATCH	/auth/roles/{id}/
DELETE	/auth/roles/{id}/
Sub-Admins (/api/admin/sub-admins/)
Method	Endpoint
GET	/admin/sub-admins/
GET	/admin/sub-admins/{id}/
POST	/admin/sub-admins/
PATCH	/admin/sub-admins/{id}/
DELETE	/admin/sub-admins/{id}/
POST	/admin/sub-admins/{id}/activate/
POST	/admin/sub-admins/{id}/deactivate/
POST	/admin/sub-admins/{id}/permissions/
GET	/admin/sub-admins/available-permissions/
Languages (/api/admin/languages/)
Method	Endpoint
GET	/admin/languages/
GET	/admin/languages/{id}/
POST	/admin/languages/
PATCH	/admin/languages/{id}/
DELETE	/admin/languages/{id}/
POST	/admin/languages/{id}/activate/
POST	/admin/languages/{id}/deactivate/
POST	/admin/languages/{id}/set_default/
Translation Categories (/api/admin/translation-categories/)
Method	Endpoint
GET	/admin/translation-categories/
GET	/admin/translation-categories/{id}/
POST	/admin/translation-categories/
PATCH	/admin/translation-categories/{id}/
DELETE	/admin/translation-categories/{id}/
Translations (/api/admin/translations/)
Method	Endpoint
GET	/admin/translations/
GET	/admin/translations/{id}/
POST	/admin/translations/
PATCH	/admin/translations/{id}/
DELETE	/admin/translations/{id}/
POST	/admin/translations/{id}/verify/
POST	/admin/translations/bulk_create/
GET	/translations/public/ — public, no auth
Menu Items (/api/admin/menu/)
Method	Endpoint
GET	/admin/menu/
GET	/admin/menu/{id}/
POST	/admin/menu/
PATCH	/admin/menu/{id}/
DELETE	/admin/menu/{id}/
POST	/admin/menu/{id}/activate/
POST	/admin/menu/{id}/deactivate/
Notification Template Codes (/api/notifications/template-codes/)
Method	Endpoint
GET/POST/PATCH/DELETE	/notifications/template-codes/ + /{id}/
POST	/notifications/template-codes/{id}/activate/
POST	/notifications/template-codes/{id}/deactivate/
Notification Templates (/api/notifications/templates/)
Method	Endpoint
GET/POST/PATCH/DELETE	/notifications/templates/ + /{id}/
POST	/notifications/templates/{id}/activate/
POST	/notifications/templates/{id}/deactivate/
POST	/notifications/templates/{id}/test_render/
Channel Settings (/api/notifications/channel-settings/)
Method	Endpoint
GET/POST/PATCH/DELETE	/notifications/channel-settings/ + /{id}/
POST	/notifications/channel-settings/{id}/activate/
POST	/notifications/channel-settings/{id}/deactivate/
POST	/notifications/channel-settings/{id}/test/
Notification Inbox (/api/notifications/inbox/)
Method	Endpoint
GET	/notifications/inbox/
GET	/notifications/inbox/{id}/
POST	/notifications/inbox/{id}/read/
POST	/notifications/inbox/read_all/
GET	/notifications/inbox/unread_count/
