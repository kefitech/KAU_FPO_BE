Login Page (/v1/login)
Type	String
Field Label	Username
Field Label	Password
Placeholder	your username
Placeholder	••••••••
Button	Sign In
Error	Invalid username or password
Languages & Translations (/admin/languages)
Page
Type	String
Page Title	Languages & Translations
Description	Manage platform languages and translation categories
Tab	Languages
Tab	Categories
Tab	Translations
Button	Add Language
Button	Add Category
Button	Export
Button	Import
Button	Add Translation
Language Dialog (Add/Edit)
Type	String
Dialog Title	Add Language / Edit Language
Field Label	Name
Field Label	Code
Field Label	Native Name
Field Label	Locale
Field Label	Display Order
Field Label	Active
Field Label	Default
Field Label	RTL
Placeholder	e.g. Malayalam
Placeholder	e.g. ml
Placeholder	e.g. മലയാളം
Placeholder	e.g. ml_IN
Button	Cancel
Button	Reset
Button	Save
Toast	Language added successfully
Toast	Language updated successfully
Toast	Language activated
Toast	Language deactivated
Toast	"X" set as default
Toast	"X" deleted
Toast	Failed to add language
Toast	Failed to delete
Toast	Action failed
Language Columns
Type	String
Column Header	Name
Column Header	Code
Column Header	Status
Column Header	Default
Dropdown Item	Edit
Dropdown Item	Set as Default
Dropdown Item	Activate
Dropdown Item	Deactivate
Dropdown Item	Delete
Badge	Active
Badge	Inactive
Badge	Default
Category Dialog (Add/Edit)
Type	String
Dialog Title	Add Category / Edit Category
Field Label	Name
Field Label	Code
Field Label	Description
Field Label	Display Order
Placeholder	e.g. Authentication
Placeholder	e.g. auth
Placeholder	Describe what translations belong here
Button	Cancel
Button	Reset
Button	Save
Toast	Category added successfully
Toast	Category updated successfully
Toast	"X" deleted
Toast	Failed to delete
Category Columns
Type	String
Column Header	Name
Column Header	Code
Column Header	Description
Column Header	Translations
Column Header	Order
Dropdown Item	Edit
Dropdown Item	Delete
Translation Dialog (Add/Edit)
Type	String
Dialog Title	Add Translation / Edit Translation
Field Label	Language
Field Label	Category
Field Label	Key
Field Label	Value
Field Label	Context (optional)
Placeholder	e.g. login_success
Placeholder	Translated text
Placeholder	e.g. Login page success message
Button	Cancel
Button	Reset
Button	Save
Toast	Translation added successfully
Toast	Translation updated successfully
Toast	Translation marked as verified
Toast	Translation deleted
Toast	Failed to verify
Toast	Failed to delete
Translation Columns
Type	String
Column Header	Key
Column Header	Language
Column Header	Category
Column Header	Value
Column Header	Status
Dropdown Item	Edit
Dropdown Item	Mark as Verified
Dropdown Item	Delete
Badge	Verified
Badge	Unverified
Export Dialog
Type	String
Dialog Title	Export Translation Template
Description	Downloads only keys that are missing translations for the selected language
Field Label	Language
Field Label	Category
Field Label	File Format
Option	All categories
Option	Excel (.xlsx)
Option	CSV (.csv)
Button	Cancel
Button	Export
Button	Downloading...
Toast	Please select a language
Toast	Export downloaded successfully
Toast	Nothing to export (from API message)
Toast	Failed to export translations
Import Dialog
Type	String
Dialog Title	Import Translations
Field Label	Language
Field Label	Category
Button	Download Template
Button	Cancel
Button	Import
Toast	Please select a language
Toast	Please select a file to upload
Toast	Only .xlsx or .csv files are allowed
Toast	Translations imported successfully
Toast	Failed to import translations
Notifications (/admin/notifications)
Page
Type	String
Page Title	Notifications
Description	Manage notification template codes and language content
Tab	Template Codes
Tab	Templates
Button	Add Template Code
Button	Add Template
Template Code Dialog (Add/Edit)
Type	String
Dialog Title	Add Template Code / Edit Template Code
Field Label	Name
Field Label	Code
Field Label	Channel
Field Label	Variables
Field Label	Description
Field Label	Active
Placeholder	e.g. FPO Application Approved
Placeholder	e.g. fpo_approved
Placeholder	e.g. user_name, fpo_name, application_id
Placeholder	When is this notification sent?
Helper Text	Comma-separated placeholder names
Option	Email
Option	SMS
Option	In-App Notification
Option	Push Notification
Button	Cancel
Button	Reset
Button	Save
Toast	Template code created successfully
Toast	Template code updated successfully
Toast	Template code activated
Toast	Template code deactivated
Toast	"X" deleted
Toast	Failed to create template code
Toast	Failed to delete
Template Code Columns
Type	String
Column Header	Name
Column Header	Channel
Column Header	Variables
Column Header	Templates
Column Header	Missing
Column Header	Status
Dropdown Item	Edit
Dropdown Item	Activate / Deactivate
Dropdown Item	Delete
Badge	Active
Badge	Inactive
Template Dialog (Add/Edit)
Type	String
Dialog Title	Add Template / Edit Template
Field Label	Template Code
Field Label	Language
Field Label	Subject
Field Label	Body
Field Label	Active
Placeholder	Select template code
Placeholder	Select language
Placeholder	e.g. Your FPO application has been approved
Placeholder	Write the notification body here. Use {variable_name} for placeholders.
Button	Cancel
Button	Reset
Button	Save
Toast	Template created successfully
Toast	Template updated successfully
Toast	Template activated
Toast	Template deactivated
Toast	Template deleted
Toast	Failed to create template
Toast	Failed to delete
Template Columns
Type	String
Column Header	Template Code
Column Header	Channel
Column Header	Language
Column Header	Subject
Column Header	Status
Dropdown Item	Edit
Dropdown Item	Test Render
Dropdown Item	Activate / Deactivate
Dropdown Item	Delete
Test Render Dialog
Type	String
Dialog Title	Test Render
Description	Enter sample values
Label	Rendered Output
Label	Subject
Label	Body
Placeholder	Sample value for {variable}
Info	This template has no variables.
Button	Close
Button	Render
Button	Rendering...
Toast	Failed to render template
Global Confirm Dialog (Delete)
Type	String
Title	Delete Language
Title	Delete Category
Title	Delete Translation
Title	Delete Template Code
Title	Delete Template
Button	Cancel
Button	Delete
Button	Deleting...
That's every user-facing string across all current admin pages. Share this with your backend team — they can create translation keys for each one.