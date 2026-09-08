"""
Navigation config API — mirrors src/config/navigation-defaults.ts on the frontend.
GET /api/v1/navigation/<portal>/
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from apps.core.utils.responses import StandardResponse

NAVIGATION_CONFIGS = {
    "fpo": {
        "logo": {"title": "KAU-FPO Platform", "subtitle": "FPO Portal", "icon": "Sprout"},
        "groups": [
            {
                "id": "main", "label": "Menu", "translations": {"ml": "മെനു"},
                "items": [
                    {"id": "dashboard", "title": "Dashboard", "translations": {"ml": "ഡാഷ്‌ബോർഡ്"}, "url": "/fpo/dashboard", "icon": "LayoutDashboard"},
                    {"id": "profile", "title": "My Profile", "translations": {"ml": "എന്റെ പ്രൊഫൈൽ"}, "url": "/fpo/profile", "icon": "User"},
                    {"id": "applications", "title": "Applications", "translations": {"ml": "അപേക്ഷകൾ"}, "url": "/fpo/applications", "icon": "FileText"},
                    {"id": "recommendations", "title": "AI Recommendations", "translations": {"ml": "AI ശുപാർശകൾ"}, "url": "/fpo/recommendations", "icon": "Lightbulb"},
                    {"id": "team", "title": "Team", "translations": {"ml": "ടീം"}, "url": "/fpo/team", "icon": "Users"},
                    {"id": "products", "title": "My Products", "translations": {"ml": "എന്റെ ഉൽപ്പന്നങ്ങൾ"}, "url": "/fpo/products", "icon": "Package"},
                    {"id": "market", "title": "Market Linkage", "translations": {"ml": "വിപണി ബന്ധം"}, "url": "/fpo/market", "icon": "Store"},
                    {"id": "schemes", "title": "Schemes", "translations": {"ml": "പദ്ധതികൾ"}, "url": "/fpo/schemes", "icon": "FileText"},
                    {"id": "experts", "title": "Expert Directory", "translations": {"ml": "വിദഗ്ധ ഡയറക്ടറി"}, "url": "/fpo/experts", "icon": "BookOpen"},
                    {"id": "tier-assessment", "title": "Tier Assessment", "translations": {"ml": "ടയർ അസസ്മെന്റ്"}, "url": "/fpo/tier-assessment", "icon": "ClipboardList"},
                ],
            },
        ],
        "footerItems": [
            {"id": "settings", "title": "Settings", "translations": {"ml": "ക്രമീകരണങ്ങൾ"}, "url": "/fpo/settings", "icon": "Settings"},
            {"id": "logout", "title": "Logout", "translations": {"ml": "ലോഗൗട്ട്"}, "url": "/logout", "icon": "LogOut"},
        ],
    },
    "admin": {
        "logo": {"title": "KAU-FPO Platform", "subtitle": "Admin Portal", "icon": "Sprout"},
        "groups": [
            {
                "id": "main", "label": "Dashboard", "translations": {"ml": "ഡാഷ്‌ബോർഡ്"},
                "items": [
                    {"id": "dashboard", "title": "Overview", "translations": {"ml": "അവലോകനം"}, "url": "/admin/dashboard", "icon": "LayoutDashboard"},
                    {"id": "analytics", "title": "Analytics", "translations": {"ml": "അനലിറ്റിക്സ്"}, "url": "/admin/analytics", "icon": "BarChart3"},
                ],
            },
            {
                "id": "management", "label": "Management", "translations": {"ml": "മാനേജ്‌മെന്റ്"},
                "items": [
                    {"id": "applications", "title": "FPO Applications", "translations": {"ml": "FPO അപേക്ഷകൾ"}, "url": "/admin/applications", "icon": "FileText", "badge": "12"},
                    {"id": "users", "title": "User Management", "translations": {"ml": "ഉപയോക്തൃ മാനേജ്‌മെന്റ്"}, "url": "/admin/users", "icon": "Users"},
                    {"id": "languages", "title": "Languages", "translations": {"ml": "ഭാഷകൾ"}, "url": "/admin/languages", "icon": "Globe"},
                    {"id": "notifications", "title": "Notifications", "translations": {"ml": "അറിയിപ്പുകൾ"}, "url": "/admin/notifications", "icon": "Bell"},
                    {"id": "experts", "title": "Expert Directory", "translations": {"ml": "വിദഗ്ധ ഡയറക്ടറി"}, "url": "/admin/experts", "icon": "User"},
                ],
            },
            {
                "id": "reports", "label": "Reports", "translations": {"ml": "റിപ്പോർട്ടുകൾ"},
                "items": [
                    {"id": "reports", "title": "Generate Reports", "translations": {"ml": "റിപ്പോർട്ടുകൾ ജനറേറ്റ് ചെയ്യുക"}, "url": "/admin/reports", "icon": "ClipboardList"},
                ],
            },
        ],
        "footerItems": [
            {"id": "settings", "title": "Settings", "translations": {"ml": "ക്രമീകരണങ്ങൾ"}, "url": "/admin/settings", "icon": "Settings"},
            {"id": "logout", "title": "Logout", "translations": {"ml": "ലോഗൗട്ട്"}, "url": "/logout", "icon": "LogOut"},
        ],
    },
    "government": {
        "logo": {"title": "KAU-FPO Platform", "subtitle": "Government Portal", "icon": "Sprout"},
        "groups": [
            {
                "id": "main", "label": "Dashboard", "translations": {"ml": "ഡാഷ്‌ബോർഡ്"},
                "items": [
                    {"id": "dashboard", "title": "Overview", "translations": {"ml": "അവലോകനം"}, "url": "/government/dashboard", "icon": "LayoutDashboard"},
                    {"id": "profile", "title": "Profile", "translations": {"ml": "പ്രൊഫൈൽ"}, "url": "/government/profile", "icon": "User"},
                ],
            },
            {
                "id": "data", "label": "Data & Reports", "translations": {"ml": "ഡാറ്റയും റിപ്പോർട്ടുകളും"},
                "items": [
                    {"id": "fpos", "title": "FPO Directory", "translations": {"ml": "FPO ഡയറക്ടറി"}, "url": "/government/fpos", "icon": "Building2"},
                    {"id": "schemes", "title": "Scheme Linkage", "translations": {"ml": "സ്കീം ലിങ്കേജ്"}, "url": "/government/schemes", "icon": "FileText"},
                    {"id": "training", "title": "Training Sessions", "translations": {"ml": "Training Sessions"}, "url": "/government/training", "icon": "GraduationCap"},
                ],
            },
        ],
        "footerItems": [
            {"id": "logout", "title": "Logout", "translations": {"ml": "ലോഗൗട്ട്"}, "url": "/logout", "icon": "LogOut"},
        ],
    },
    "cbbo": {
        "logo": {"title": "KAU-FPO Platform", "subtitle": "CBBO/NGO Portal", "icon": "Sprout"},
        "groups": [
            {
                "id": "main", "label": "Dashboard", "translations": {"ml": "ഡാഷ്‌ബോർഡ്"},
                "items": [
                    {"id": "dashboard", "title": "Overview", "translations": {"ml": "അവലോകനം"}, "url": "/cbbo/dashboard", "icon": "LayoutDashboard"},
                ],
            },
            {
                "id": "tasks", "label": "Tasks", "translations": {"ml": "ടാസ്കുകൾ"},
                "items": [
                    {"id": "verifications", "title": "FPO Verifications", "translations": {"ml": "FPO വെരിഫിക്കേഷനുകൾ"}, "url": "/cbbo/verifications", "icon": "CheckCircle"},
                    {"id": "reports", "title": "Reports", "translations": {"ml": "റിപ്പോർട്ടുകൾ"}, "url": "/cbbo/reports", "icon": "ClipboardList"},
                    {"id": "profile", "title": "Profile", "translations": {"ml": "പ്രൊഫൈൽ"}, "url": "/cbbo/profile", "icon": "User"},
                ],
            },
        ],
        "footerItems": [
            
            {"id": "logout", "title": "Logout", "translations": {"ml": "ലോഗൗട്ട്"}, "url": "/logout", "icon": "LogOut"},
        ],
    },
    "expert": {
        "logo": {"title": "KAU-FPO Platform", "subtitle": "Expert Portal", "icon": "Sprout"},
        "groups": [
            {
                "id": "main", "label": "Dashboard", "translations": {"ml": "ഡാഷ്‌ബോർഡ്"},
                "items": [
                    {"id": "dashboard", "title": "My Bookings", "translations": {"ml": "എന്റെ ബുക്കിംഗുകൾ"}, "url": "/expert/dashboard", "icon": "LayoutDashboard"},
                    {"id": "availability", "title": "Availability", "translations": {"ml": "ലഭ്യത"}, "url": "/expert/availability", "icon": "CalendarDays"},
                    {"id": "profile", "title": "Profile", "translations": {"ml": "പ്രൊഫൈൽ"}, "url": "/expert/profile", "icon": "User"},
                ],
            },
        ],
        "footerItems": [
            {"id": "logout", "title": "Logout", "translations": {"ml": "ലോഗൗട്ട്"}, "url": "/logout", "icon": "LogOut"},
        ],
    },
}


class PortalNavigationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Navigation'], summary='Get navigation config for a portal')
    def get(self, request, portal):
        config = NAVIGATION_CONFIGS.get(portal)
        if not config:
            return StandardResponse.error('Unknown portal type.', status_code=404)
        return StandardResponse.success(data=config)
