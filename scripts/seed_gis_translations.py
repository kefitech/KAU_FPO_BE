"""
Seed GIS Translation Keys — admin_gis_zones + fpo_gis screens
================================================================
Follows the exact same pattern as scripts/seed_ml_ui_translations.py:
one shared TranslationCategory (code='ui'), screen name as a key
prefix (e.g. 'admin_gis_zones.page_title'). Seeds BOTH English and
Malayalam, since these are entirely new keys (not gap-filling
existing ones).

HONEST NOTE: Malayalam values below are a best-effort AI translation,
not reviewed by a native speaker — worth a real review pass before
treating as final, same caveat as anything else translated tonight.

Usage:
    python manage.py shell -c "
    exec(open('scripts/seed_gis_translations.py').read())
    seed_gis_translations()"
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.database.models import Language, TranslationCategory, Translation


def seed_gis_translations():
    lang_en = Language.objects.get(code='en')
    lang_ml = Language.objects.get(code='ml')
    category = TranslationCategory.objects.get(code='ui')

    screens = {
        # ── Admin: GIS zone boundary management ──
        'admin_gis_zones': {
            'page_title':              ('Agro-Climatic Zone Boundaries', 'അഗ്രോ-ക്ലൈമാറ്റിക് സോൺ അതിരുകൾ'),
            'page_description':        ('Click a row below to preview it on the map — this does NOT make it live. Only "Activate" does that.', 'താഴെയുള്ള ഒരു വരി ക്ലിക്ക് ചെയ്ത് മാപ്പിൽ പ്രിവ്യൂ കാണുക — ഇത് തത്സമയമാക്കില്ല. "സജീവമാക്കുക" മാത്രമേ അത് ചെയ്യൂ.'),
            'btn_upload':               ('Upload new version', 'പുതിയ പതിപ്പ് അപ്‌ലോഡ് ചെയ്യുക'),
            'preview_banner':           ('Previewing {label} — not live, farmers still see the current active zones.', '{label} പ്രിവ്യൂ ചെയ്യുന്നു — തത്സമയമല്ല, കർഷകർ ഇപ്പോഴും നിലവിലെ സജീവ സോണുകൾ കാണുന്നു.'),
            'btn_back_to_live':         ('Back to live view', 'തത്സമയ കാഴ്ചയിലേക്ക് മടങ്ങുക'),
            'live_banner':              ('Showing the currently LIVE zones — what every farmer sees right now.', 'നിലവിൽ തത്സമയമായ സോണുകൾ കാണിക്കുന്നു — എല്ലാ കർഷകരും ഇപ്പോൾ കാണുന്നത്.'),
            'versions_heading':         ('Uploaded Versions', 'അപ്‌ലോഡ് ചെയ്ത പതിപ്പുകൾ'),
            'versions_description':    ('Click a row to preview it above. Use the ⋯ menu to Activate or Delete.', 'മുകളിൽ പ്രിവ്യൂ ചെയ്യാൻ ഒരു വരി ക്ലിക്ക് ചെയ്യുക. സജീവമാക്കാനോ ഇല്ലാതാക്കാനോ ⋯ മെനു ഉപയോഗിക്കുക.'),
            'col_file':                 ('File', 'ഫയൽ'),
            'col_uploaded':             ('Uploaded', 'അപ്‌ലോഡ് ചെയ്തത്'),
            'badge_active':             ('Active', 'സജീവം'),
            'badge_inactive':           ('Inactive', 'നിഷ്ക്രിയം'),
            'action_activate':          ('Activate', 'സജീവമാക്കുക'),
            'action_delete':            ('Delete', 'ഇല്ലാതാക്കുക'),
            'delete_confirm_title':     ('Delete Zone Version', 'സോൺ പതിപ്പ് ഇല്ലാതാക്കുക'),
            'delete_confirm_desc':      ('Are you sure you want to delete "{label}"? This cannot be undone.', '"{label}" ഇല്ലാതാക്കണമെന്ന് ഉറപ്പാണോ? ഇത് പഴയപടിയാക്കാൻ കഴിയില്ല.'),
            'toast_uploaded':           ('Uploaded "{label}" — not yet live. Click a row to preview, or Activate when ready.', '"{label}" അപ്‌ലോഡ് ചെയ്തു — ഇതുവരെ തത്സമയമല്ല. പ്രിവ്യൂ ചെയ്യാൻ ഒരു വരി ക്ലിക്ക് ചെയ്യുക, തയ്യാറാകുമ്പോൾ സജീവമാക്കുക.'),
            'toast_activated':         ('Zones updated: {zones}', 'സോണുകൾ അപ്ഡേറ്റ് ചെയ്തു: {zones}'),
            'toast_deleted':            ('Deleted "{label}"', '"{label}" ഇല്ലാതാക്കി'),
            'toast_upload_failed':      ('Failed to upload zone boundaries', 'സോൺ അതിരുകൾ അപ്‌ലോഡ് ചെയ്യുന്നത് പരാജയപ്പെട്ടു'),
            'toast_activate_failed':    ('Failed to activate this version', 'ഈ പതിപ്പ് സജീവമാക്കുന്നത് പരാജയപ്പെട്ടു'),
            'toast_delete_failed':      ('Failed to delete this version', 'ഈ പതിപ്പ് ഇല്ലാതാക്കുന്നത് പരാജയപ്പെട്ടു'),
            'map_hide_zones':           ('Hide zones', 'സോണുകൾ മറയ്ക്കുക'),
            'map_show_zones':           ('Show zones', 'സോണുകൾ കാണിക്കുക'),
            'map_opacity':              ('Opacity', 'അതാര്യത'),
            'map_satellite_tooltip':    ('Switch to satellite view', 'സാറ്റലൈറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'map_street_tooltip':       ('Switch to street view', 'സ്ട്രീറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'map_recenter_tooltip':     ('Recenter on all zones', 'എല്ലാ സോണുകളിലേക്കും വീണ്ടും കേന്ദ്രീകരിക്കുക'),
            'map_expand_tooltip':       ('Expand map', 'മാപ്പ് വലുതാക്കുക'),
            'map_exit_fullscreen_tooltip': ('Exit fullscreen', 'ഫുൾസ്ക്രീനിൽ നിന്ന് പുറത്തുകടക്കുക'),
            'search_placeholder':       ('Search a place…', 'ഒരു സ്ഥലം തിരയുക…'),
            'search_no_results':        ('No places found.', 'സ്ഥലങ്ങളൊന്നും കണ്ടെത്തിയില്ല.'),
            'search_searching':         ('Searching…', 'തിരയുന്നു…'),
        },

        # ── Admin: soil region management (P2-05 follow-up — soil split out
        # of AgroClimaticZone into its own independent polygon layer) ──
        'admin_soil_regions': {
            'page_title':              ('Soil Regions', 'മണ്ണ് പ്രദേശങ്ങൾ'),
            'page_description':        ('Soil type by location, independent of agro-climatic zone boundaries. Click a row below to preview it on the map — this does NOT make it live. Only "Activate" does that.', 'അഗ്രോ-ക്ലൈമാറ്റിക് സോൺ അതിരുകളിൽ നിന്ന് സ്വതന്ത്രമായി, സ്ഥലം അനുസരിച്ചുള്ള മണ്ണ് തരം. താഴെയുള്ള ഒരു വരി ക്ലിക്ക് ചെയ്ത് മാപ്പിൽ പ്രിവ്യൂ കാണുക — ഇത് തത്സമയമാക്കില്ല. "സജീവമാക്കുക" മാത്രമേ അത് ചെയ്യൂ.'),
            'btn_upload':               ('Upload new version', 'പുതിയ പതിപ്പ് അപ്‌ലോഡ് ചെയ്യുക'),
            'preview_banner':           ('Previewing {label} — not live, farmers still see the current active soil regions.', '{label} പ്രിവ്യൂ ചെയ്യുന്നു — തത്സമയമല്ല, കർഷകർ ഇപ്പോഴും നിലവിലെ സജീവ മണ്ണ് പ്രദേശങ്ങൾ കാണുന്നു.'),
            'btn_back_to_live':         ('Back to live view', 'തത്സമയ കാഴ്ചയിലേക്ക് മടങ്ങുക'),
            'live_banner':              ('Showing the currently LIVE soil regions — what every recommendation lookup uses right now.', 'നിലവിൽ തത്സമയമായ മണ്ണ് പ്രദേശങ്ങൾ കാണിക്കുന്നു — ഓരോ ശുപാർശ തിരയലും ഇപ്പോൾ ഉപയോഗിക്കുന്നത്.'),
            'versions_heading':         ('Uploaded Versions', 'അപ്‌ലോഡ് ചെയ്ത പതിപ്പുകൾ'),
            'versions_description':    ('Click a row to preview it above. Use the ⋯ menu to Activate or Delete.', 'മുകളിൽ പ്രിവ്യൂ ചെയ്യാൻ ഒരു വരി ക്ലിക്ക് ചെയ്യുക. സജീവമാക്കാനോ ഇല്ലാതാക്കാനോ ⋯ മെനു ഉപയോഗിക്കുക.'),
            'col_file':                 ('File', 'ഫയൽ'),
            'col_uploaded':             ('Uploaded', 'അപ്‌ലോഡ് ചെയ്തത്'),
            'badge_active':             ('Active', 'സജീവം'),
            'badge_inactive':           ('Inactive', 'നിഷ്ക്രിയം'),
            'action_activate':          ('Activate', 'സജീവമാക്കുക'),
            'action_delete':            ('Delete', 'ഇല്ലാതാക്കുക'),
            'delete_confirm_title':     ('Delete Soil Region Version', 'മണ്ണ് പ്രദേശ പതിപ്പ് ഇല്ലാതാക്കുക'),
            'delete_confirm_desc':      ('Are you sure you want to delete "{label}"? This cannot be undone.', '"{label}" ഇല്ലാതാക്കണമെന്ന് ഉറപ്പാണോ? ഇത് പഴയപടിയാക്കാൻ കഴിയില്ല.'),
            'toast_uploaded':           ('Uploaded "{label}" — not yet live.', '"{label}" അപ്‌ലോഡ് ചെയ്തു — ഇതുവരെ തത്സമയമല്ല.'),
            'toast_upload_failed':      ('Failed to upload soil regions', 'മണ്ണ് പ്രദേശങ്ങൾ അപ്‌ലോഡ് ചെയ്യുന്നത് പരാജയപ്പെട്ടു'),
            'toast_activated':         ('Soil regions updated: {regions}', 'മണ്ണ് പ്രദേശങ്ങൾ അപ്ഡേറ്റ് ചെയ്തു: {regions}'),
            'toast_activate_failed':    ('Failed to activate this version', 'ഈ പതിപ്പ് സജീവമാക്കുന്നത് പരാജയപ്പെട്ടു'),
            'toast_deleted':            ('Deleted "{label}"', '"{label}" ഇല്ലാതാക്കി'),
            'toast_delete_failed':      ('Failed to delete this version', 'ഈ പതിപ്പ് ഇല്ലാതാക്കുന്നത് പരാജയപ്പെട്ടു'),
            'map_hide_regions':         ('Hide soil regions', 'മണ്ണ് പ്രദേശങ്ങൾ മറയ്ക്കുക'),
            'map_show_regions':         ('Show soil regions', 'മണ്ണ് പ്രദേശങ്ങൾ കാണിക്കുക'),
            'map_opacity':              ('Opacity', 'അതാര്യത'),
            'map_satellite_tooltip':    ('Switch to satellite view', 'സാറ്റലൈറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'map_street_tooltip':       ('Switch to street view', 'സ്ട്രീറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'map_recenter_tooltip':     ('Recenter on all soil regions', 'എല്ലാ മണ്ണ് പ്രദേശങ്ങളിലേക്കും വീണ്ടും കേന്ദ്രീകരിക്കുക'),
            'map_expand_tooltip':       ('Expand map', 'മാപ്പ് വലുതാക്കുക'),
            'map_exit_fullscreen_tooltip': ('Exit fullscreen', 'ഫുൾസ്ക്രീനിൽ നിന്ന് പുറത്തുകടക്കുക'),
            'search_placeholder':       ('Search a place…', 'ഒരു സ്ഥലം തിരയുക…'),
            'search_no_results':        ('No places found.', 'സ്ഥലങ്ങളൊന്നും കണ്ടെത്തിയില്ല.'),
            'search_searching':         ('Searching…', 'തിരയുന്നു…'),
        },

        # ── FPO: recommendations page chrome (title, tabs, section headings) ──
        'fpo_recommendations': {
            'page_title':                ('AI Recommendations', 'AI ശുപാർശകൾ'),
            'page_description':          ('Get AI-powered crop recommendations, business plan guidance, and DPR generation.', 'AI പ്രവർത്തിത വിള ശുപാർശകൾ, ബിസിനസ് പ്ലാൻ മാർഗ്ഗനിർദ്ദേശം, DPR നിർമ്മാണം എന്നിവ നേടുക.'),
            'tab_crop_recommendation':   ('Crop Recommendation', 'വിള ശുപാർശ'),
            'tab_business_plan':         ('Business Plan Guidance', 'ബിസിനസ് പ്ലാൻ മാർഗ്ഗനിർദ്ദേശം'),
            'tab_dpr_generation':        ('DPR Generation', 'DPR നിർമ്മാണം'),
            'farm_boundary_heading':     ('Your Farm Boundary', 'നിങ്ങളുടെ കൃഷിയിടത്തിന്റെ അതിര്'),
            'farm_boundary_description': ('Mark your cultivation area on the map — this helps us tailor crop recommendations to your farm.', 'മാപ്പിൽ നിങ്ങളുടെ കൃഷിസ്ഥലം അടയാളപ്പെടുത്തുക — ഇത് നിങ്ങളുടെ കൃഷിയിടത്തിന് അനുയോജ്യമായ വിള ശുപാർശകൾ നൽകാൻ സഹായിക്കുന്നു.'),
            'business_plan_coming_soon': ('Business Plan Guidance — coming soon.', 'ബിസിനസ് പ്ലാൻ മാർഗ്ഗനിർദ്ദേശം — ഉടൻ വരുന്നു.'),
            'dpr_coming_soon':           ('DPR Generation — coming soon.', 'DPR നിർമ്മാണം — ഉടൻ വരുന്നു.'),

            # ── Crop Recommendation Display (crop-recommendation-display.tsx) ──
            'title':                     ('AI Crop Recommendations', 'AI വിള ശുപാർശകൾ'),
            'for_financial_year':        ('For financial year {fy}', 'സാമ്പത്തിക വർഷം {fy}'),
            'generated_for_season':      ('— generated for {season}', '— {season} സീസണിനായി തയ്യാറാക്കിയത്'),
            'season_aria_label':         ('Season', 'സീസൺ'),
            'season_auto':               ('Auto-detect', 'സ്വയമേവ കണ്ടെത്തുക'),
            'season_sw_monsoon':         ('South-West Monsoon', 'തെക്കുപടിഞ്ഞാറൻ മൺസൂൺ'),
            'season_ne_monsoon':         ('North-East Monsoon', 'വടക്കുകിഴക്കൻ മൺസൂൺ'),
            'season_dry':                ('Dry Season', 'വരണ്ട കാലം'),
            'btn_get':                   ('Get recommendations', 'ശുപാർശകൾ നേടുക'),
            'btn_refresh':               ('Refresh recommendations', 'ശുപാർശകൾ പുതുക്കുക'),
            'error_load':                ('Could not load your recommendation.', 'നിങ്ങളുടെ ശുപാർശ ലോഡ് ചെയ്യാനായില്ല.'),
            'error_generic':             ('Could not get a recommendation right now. Please try again.', 'ഇപ്പോൾ ശുപാർശ ലഭിക്കാനായില്ല. വീണ്ടും ശ്രമിക്കുക.'),
            'error_outside_kerala':      ('Crop recommendations are only available for locations within Kerala. Check your cultivation area boundary above.', 'വിള ശുപാർശകൾ കേരളത്തിനുള്ളിലെ സ്ഥലങ്ങൾക്ക് മാത്രമേ ലഭ്യമാകൂ. മുകളിലുള്ള നിങ്ങളുടെ കൃഷിസ്ഥല അതിര് പരിശോധിക്കുക.'),
            'stale_notice':              ("Showing your previous recommendation below — the request above failed, so this hasn't changed.", 'താഴെ നിങ്ങളുടെ മുൻ ശുപാർശ കാണിക്കുന്നു — മുകളിലെ അഭ്യർത്ഥന പരാജയപ്പെട്ടു, അതിനാൽ ഇത് മാറ്റമില്ലാതെ തുടരുന്നു.'),
            'warning_service_unavailable': ('Showing your last saved recommendation — the AI service is temporarily unavailable.', 'നിങ്ങളുടെ അവസാനം സേവ് ചെയ്ത ശുപാർശ കാണിക്കുന്നു — AI സേവനം താൽക്കാലികമായി ലഭ്യമല്ല.'),
            'empty_title':               ('No recommendations yet.', 'ഇതുവരെ ശുപാർശകളൊന്നുമില്ല.'),
            'empty_description':         ('Click "Get recommendations" above — accuracy improves if you\'ve drawn your cultivation area above.', 'മുകളിൽ "ശുപാർശകൾ നേടുക" ക്ലിക്ക് ചെയ്യുക — മുകളിൽ നിങ്ങളുടെ കൃഷിസ്ഥലം വരച്ചിട്ടുണ്ടെങ്കിൽ കൃത്യത മെച്ചപ്പെടും.'),
            'working_title':             ('Generating your recommendation…', 'നിങ്ങളുടെ ശുപാർശ തയ്യാറാക്കുന്നു…'),
            'working_description':       ("This runs in the background — you'll also get a notification when it's ready.", 'ഇത് പശ്ചാത്തലത്തിൽ പ്രവർത്തിക്കുന്നു — തയ്യാറാകുമ്പോൾ നിങ്ങൾക്ക് അറിയിപ്പും ലഭിക്കും.'),
            'outside_kerala_title':      ('Crop recommendations are only available for locations within Kerala.', 'വിള ശുപാർശകൾ കേരളത്തിനുള്ളിലെ സ്ഥലങ്ങൾക്ക് മാത്രമേ ലഭ്യമാകൂ.'),
            'outside_kerala_description': ("Check your cultivation area boundary above — it looks like it falls outside Kerala's supported zones.", 'മുകളിലുള്ള നിങ്ങളുടെ കൃഷിസ്ഥല അതിര് പരിശോധിക്കുക — ഇത് കേരളത്തിന്റെ പിന്തുണയുള്ള സോണുകൾക്ക് പുറത്താണെന്ന് തോന്നുന്നു.'),
            'failed_title':              ("Couldn't generate a recommendation this time.", 'ഈ തവണ ശുപാർശ തയ്യാറാക്കാനായില്ല.'),
            'failed_description':        ('Try again using the button above.', 'മുകളിലുള്ള ബട്ടൺ ഉപയോഗിച്ച് വീണ്ടും ശ്രമിക്കുക.'),
            'confidence_match':          ('{pct}% match', '{pct}% പൊരുത്തം'),
            'estimated_yield_label':     ('Estimated yield:', 'കണക്കാക്കിയ വിളവ്:'),
            'feedback_title_new':        ('Was this helpful?', 'ഇത് സഹായകരമായിരുന്നോ?'),
            'feedback_title_submitted':  ('Your feedback', 'നിങ്ങളുടെ അഭിപ്രായം'),
            'feedback_comment_placeholder': ('Any comments? (optional)', 'എന്തെങ്കിലും അഭിപ്രായങ്ങൾ? (ഓപ്ഷണൽ)'),
            'feedback_submit':           ('Submit feedback', 'അഭിപ്രായം സമർപ്പിക്കുക'),
            'feedback_submitting':       ('Submitting…', 'സമർപ്പിക്കുന്നു…'),
            'feedback_thanks':           ('Thanks for your feedback!', 'നിങ്ങളുടെ അഭിപ്രായത്തിന് നന്ദി!'),
            'rate_star_aria':            ('Rate {n} star(s)', '{n} നക്ഷത്രം(ങ്ങൾ) റേറ്റ് ചെയ്യുക'),
            'location_map_label':        ('Farm location at time of this recommendation', 'ഈ ശുപാർശ നൽകിയ സമയത്തെ കൃഷിയിട സ്ഥാനം'),
        },

        # ── FPO: cultivation area map / zone-related labels ──
        'fpo_gis': {
            'draw_prompt':              ("Draw your farm's boundary to help us give more accurate recommendations.", 'കൂടുതൽ കൃത്യമായ ശുപാർശകൾ നൽകാൻ നിങ്ങളുടെ കൃഷിയിടത്തിന്റെ അതിര് വരയ്ക്കുക.'),
            'draw_saved':                ('This is your saved cultivation area.', 'ഇത് നിങ്ങൾ സേവ് ചെയ്ത കൃഷിസ്ഥലമാണ്.'),
            'draw_instruction':          ('Click the map to place each corner of your farm boundary.', 'നിങ്ങളുടെ കൃഷിയിടത്തിന്റെ ഓരോ കോണും അടയാളപ്പെടുത്താൻ മാപ്പിൽ ക്ലിക്ക് ചെയ്യുക.'),
            'btn_draw_boundary':         ('Draw boundary', 'അതിര് വരയ്ക്കുക'),
            'btn_redraw_boundary':       ('Redraw boundary', 'അതിര് വീണ്ടും വരയ്ക്കുക'),
            'btn_undo_point':            ('Undo point', 'പോയിന്റ് പിന്മടക്കുക'),
            'btn_cancel':                ('Cancel', 'റദ്ദാക്കുക'),
            'btn_save_boundary':         ('Save boundary', 'അതിര് സേവ് ചെയ്യുക'),
            'btn_add_more_points':       ('Add {n} more point(s)', 'ഇനി {n} പോയിന്റ്(കൾ) ചേർക്കുക'),
            'btn_delete':                ('Delete', 'ഇല്ലാതാക്കുക'),
            'label_area':                ('Area', 'വിസ്തീർണ്ണം'),
            'label_hectares':            ('hectares', 'ഹെക്ടർ'),
            'label_region':              ('Region', 'പ്രദേശം'),
            'label_soil':                ('Soil', 'മണ്ണ്'),
            'error_load_area':           ('Could not load your saved cultivation area.', 'നിങ്ങളുടെ സേവ് ചെയ്ത കൃഷിസ്ഥലം ലോഡ് ചെയ്യാനായില്ല.'),
            'error_save_area':           ('Could not save your cultivation area. Please try again.', 'നിങ്ങളുടെ കൃഷിസ്ഥലം സേവ് ചെയ്യാനായില്ല. വീണ്ടും ശ്രമിക്കുക.'),
            'error_delete_area':         ('Could not delete your cultivation area. Please try again.', 'നിങ്ങളുടെ കൃഷിസ്ഥലം ഇല്ലാതാക്കാനായില്ല. വീണ്ടും ശ്രമിക്കുക.'),
            'weather_title':             ('Weather & Season', 'കാലാവസ്ഥയും സീസണും'),
            'weather_refresh':           ('Refresh', 'പുതുക്കുക'),
            'weather_no_data':           ('No weather data yet.', 'ഇതുവരെ കാലാവസ്ഥാ വിവരങ്ങൾ ഇല്ല.'),
            'weather_check_now':         ('Check now', 'ഇപ്പോൾ പരിശോധിക്കുക'),
            'weather_simulated_note':    ('Estimated from seasonal patterns, not a live forecast.', 'സീസണൽ പാറ്റേണുകളിൽ നിന്ന് കണക്കാക്കിയത്, തത്സമയ പ്രവചനമല്ല.'),
            'weather_error':             ('Could not fetch weather. Please try again.', 'കാലാവസ്ഥ ലഭിക്കാനായില്ല. വീണ്ടും ശ്രമിക്കുക.'),
            'weather_error_load':        ('Could not load weather.', 'കാലാവസ്ഥ ലോഡ് ചെയ്യാനായില്ല.'),
            'season_sw_monsoon':         ('South-West Monsoon', 'തെക്കുപടിഞ്ഞാറൻ മൺസൂൺ'),
            'season_ne_monsoon':         ('North-East Monsoon', 'വടക്കുകിഴക്കൻ മൺസൂൺ'),
            'season_dry':                ('Dry Season', 'വരണ്ട കാലം'),
            'map_hide_zones':            ('Hide zones', 'സോണുകൾ മറയ്ക്കുക'),
            'map_show_zones':            ('Show zones', 'സോണുകൾ കാണിക്കുക'),
            'map_opacity':               ('Opacity', 'അതാര്യത'),
            'map_recenter_tooltip':      ('Recenter on my farm boundary', 'എന്റെ കൃഷിയിടത്തിന്റെ അതിരിലേക്ക് വീണ്ടും കേന്ദ്രീകരിക്കുക'),
            'map_expand_tooltip':        ('Expand map', 'മാപ്പ് വലുതാക്കുക'),
            'map_exit_fullscreen_tooltip': ('Exit fullscreen', 'ഫുൾസ്ക്രീനിൽ നിന്ന് പുറത്തുകടക്കുക'),
            'map_satellite_tooltip':     ('Switch to satellite view', 'സാറ്റലൈറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'map_street_tooltip':        ('Switch to street view', 'സ്ട്രീറ്റ് വ്യൂവിലേക്ക് മാറുക'),
            'search_placeholder':        ('Search a place…', 'ഒരു സ്ഥലം തിരയുക…'),
            'search_no_results':         ('No places found.', 'സ്ഥലങ്ങളൊന്നും കണ്ടെത്തിയില്ല.'),
            'search_searching':          ('Searching…', 'തിരയുന്നു…'),
            'boundary_click_prompt':     ('Click on the map to start marking your boundary', 'നിങ്ങളുടെ അതിര് അടയാളപ്പെടുത്താൻ മാപ്പിൽ ക്ലിക്ക് ചെയ്യുക'),
        },
    }

    count = 0
    created = 0
    updated = 0

    for screen, entries in screens.items():
        for key, (en_value, ml_value) in entries.items():
            full_key = f'{screen}.{key}'

            _, was_created_en = Translation.objects.update_or_create(
                category=category, key=full_key, language=lang_en,
                defaults={'value': en_value, 'context': 'Frontend UI label (GIS)', 'is_verified': True}
            )
            _, was_created_ml = Translation.objects.update_or_create(
                category=category, key=full_key, language=lang_ml,
                defaults={'value': ml_value, 'context': 'Frontend UI label (GIS)', 'is_verified': False}
            )

            count += 2
            created += int(was_created_en) + int(was_created_ml)
            updated += int(not was_created_en) + int(not was_created_ml)

    print(f"\n✅ GIS translations seeded: {count} total ({created} created, {updated} updated)")
    print(f"   Screens: {list(screens.keys())}")

    try:
        from django.core.cache import cache
        cache.delete_pattern('translations:public:*') if hasattr(cache, 'delete_pattern') else None
        print("✅ Redis cache cleared for translations")
    except Exception:
        print("ℹ️  Redis cache not cleared — restart server to apply")

    return count