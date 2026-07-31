def seed_block_ml_translations():
    from apps.database.models import Language, TranslationCategory, Translation

    lang_ml = Language.objects.get(code='ml')
    cat_block = TranslationCategory.objects.get(code='block')
    BLOCK_TRANSLATIONS_ML = {

    # Alappuzha (ALP)
    "ambalappuzha": "അമ്പലപ്പുഴ",
    "aryad": "ആര്യാട്",
    "bharanikkavu": "ഭരണിക്കാവ്",
    "champakulam": "ചമ്പക്കുളം",
    "chengannur": "ചെങ്ങന്നൂർ",
    "harippad": "ഹരിപ്പാട്",
    "kanjikuzhy": "കഞ്ഞിക്കുഴി",
    "mavelikkara": "മാവേലിക്കര",
    "muthukulam": "മുതുകുളം",
    "pattanakkad": "പട്ടണക്കാട്",
    "thycattussery": "തൈക്കാട്ടുശ്ശേരി",
    "veliyanad": "വേളിയനാട്",

    # Ernakulam (EKM)
    "alangad": "ആലങ്ങാട്",
    "angamaly": "അങ്കമാലി",
    "edappally": "ഇടപ്പള്ളി",
    "koovappady": "കൂവപ്പടി",
    "kothamangalam": "കോതമംഗലം",
    "mulanthuruthy": "മുളന്തുരുത്തി",
    "muvattupuzha": "മൂവാറ്റുപുഴ",
    "palluruthy": "പള്ളുരുത്തി",
    "pampakuda": "പാമ്പാക്കുട",
    "parakkadavu": "പറക്കടവ്",
    "paravur": "പറവൂർ",
    "vadavucode": "വടവുകോട്",
    "vazhakulam": "വാഴക്കുളം",
    "vypin": "വൈപ്പിൻ",

    # Idukki (IDK)
    "adimali": "അടിമാലി",
    "azhutha": "അഴുത",
    "devikulam": "ദേവികുളം",
    "elemdesam": "എളംദേശം",
    "idukki": "ഇടുക്കി",
    "kattappana": "കട്ടപ്പന",
    "nedumkandam": "നെടുങ്കണ്ടം",
    "thodupuzha": "തൊടുപുഴ",

    # Kannur (KNR)
    "edakkad": "എടക്കാട്",
    "irikkur": "ഇരിക്കൂർ",
    "iritty": "ഇരിട്ടി",
    "kalliasseri": "കല്ല്യാശ്ശേരി",
    "kannur": "കണ്ണൂർ",
    "kuthuparamba": "കൂത്തുപറമ്പ്",
    "panoor": "പാനൂർ",
    "payyannur": "പയ്യന്നൂർ",
    "peravoor": "പേരാവൂർ",
    "taliparamba": "തളിപ്പറമ്പ്",
    "thalassery": "തലശ്ശേരി",

    # Kasaragod (KSD)
    "kanhangad": "കാഞ്ഞങ്ങാട്",
    "karadka": "കാറഡുക്ക",
    "kasaragod": "കാസർഗോഡ്",
    "manjeshwar": "മഞ്ചേശ്വരം",
    "nileshwara": "നീലേശ്വരം",
    "parappa": "പരപ്പ",

    # Kollam (KLM)
    "anchal": "അഞ്ചൽ",
    "chadayamangalam": "ചടയമംഗലം",
    "chavara": "ചവറ",
    "chittumala": "ചിറ്റുമല",
    "ithikkara": "ഇത്തിക്കര",
    "kottarakkara": "കൊട്ടാരക്കര",
    "mukhathala": "മുഖത്തല",
    "oachira": "ഓച്ചിറ",
    "pathanapuram": "പത്തനാപുരം",
    "sasthamcottah": "ശാസ്താംകോട്ട",
    "vettikkavala": "വെറ്റിക്കവല",

    # Kottayam (KTM)
    "erattupetta": "ഈരാറ്റുപേട്ട",
    "ettumanoor": "ഏറ്റുമാനൂർ",
    "kaduthuruthy": "കടുത്തുരുത്തി",
    "kanjirappally": "കാഞ്ഞിരപ്പള്ളി",
    "lalam": "ലാലം",
    "madappally": "മാടപ്പള്ളി",
    "pallom": "പള്ളം",
    "pampady": "പാമ്പാടി",
    "uzhavoor": "ഉഴവൂർ",
    "vaikom": "വൈക്കം",
    "vazhoor": "വാഴൂർ",

    # Kozhikode (KZD)
    "balusseri": "ബാലുശ്ശേരി",
    "chelannur": "ചേളന്നൂർ",
    "koduvally": "കൊടുവള്ളി",
    "kozhikode": "കോഴിക്കോട്",
    "kunnamangalam": "കുന്നമംഗലം",
    "kunnummal": "കുന്നുമ്മൽ",
    "melady": "മേലടി",
    "panthalayani": "പന്തലായനി",
    "perambra": "പേരാമ്പ്ര",
    "thodannur": "തോടന്നൂർ",
    "thuneri": "തൂണേരി",
    "vadakara": "വടകര",

    # Malappuram (MLP)
    "areakode": "അരീക്കോട്",
    "kalikavu": "കാളികാവ്",
    "kondotty": "കൊണ്ടോട്ടി",
    "kuttippuram": "കുറ്റിപ്പുറം",
    "malappuram": "മലപ്പുറം",
    "mankada": "മങ്കട",
    "nilambur": "നിലമ്പൂർ",
    "perinthalmanna": "പെരിന്തൽമണ്ണ",
    "perumpadappu": "പെരുമ്പടപ്പ്",
    "ponnani": "പൊന്നാനി",
    "tanur": "താനൂർ",
    "tirur": "തിരൂർ",
    "tirurangadi": "തിരൂരങ്ങാടി",
    "vengara": "വേങ്ങര",
    "wandoor": "വണ്ടൂർ",

    # Palakkad (PKD)
    "alathur": "ആലത്തൂർ",
    "attappadi": "അട്ടപ്പാടി",
    "chittur": "ചിറ്റൂർ",
    "kollengode": "കൊല്ലങ്കോട്",
    "kuzhalmannam": "കുഴൽമന്ദം",
    "malampuzha": "മലമ്പുഴ",
    "mannarkad": "മണ്ണാർക്കാട്",
    "nemmara": "നെന്മാറ",
    "ottappalam": "ഒറ്റപ്പാലം",
    "palakkad": "പാലക്കാട്",
    "pattambi": "പട്ടാമ്പി",
    "sreekrishnapuram": "ശ്രീകൃഷ്ണപുരം",
    "trithala": "തൃത്താല",

    # Pathanamthitta (PTA)
    "elanthoor": "ഇലന്തൂർ",
    "koipuram": "കോയിപ്രം",
    "konni": "കോന്നി",
    "mallappally": "മല്ലപ്പള്ളി",
    "pandalam": "പന്തളം",
    "parakode": "പറക്കോട്",
    "pulikeezhu": "പുലിക്കീഴ്",
    "ranni": "റാന്നി",

    # Thiruvananthapuram (TVM)
    "athiyannur": "അതിയന്നൂർ",
    "chirayinkeezhu": "ചിറയിൻകീഴ്",
    "kilimanoor": "കിളിമാനൂർ",
    "nedumangad": "നെടുമങ്ങാട്",
    "nemom": "നേമം",
    "parassala": "പാറശ്ശാല",
    "perumkadavila": "പെരുങ്കടവിള",
    "pothencode": "പോത്തൻകോട്",
    "vamanapuram": "വാമനപുരം",
    "varkala": "വർക്കല",
    "vellanad": "വെള്ളനാട്",

    # Thrissur (TSR)
    "anthikkad": "അന്തിക്കാട്",
    "chalakudy": "ചാലക്കുടി",
    "chavakkad": "ചാവക്കാട്",
    "cherpu": "ചേർപ്പ്",
    "chowannur": "ചൊവ്വന്നൂർ",
    "irinjalakkuda": "ഇരിഞ്ഞാലക്കുട",
    "kodakara": "കൊടകര",
    "mala": "മാള",
    "mathilakam": "മതിലകം",
    "mullassery": "മുല്ലശ്ശേരി",
    "ollukkara": "ഒല്ലൂക്കര",
    "pazhayannur": "പഴയന്നൂർ",
    "puzhakkal": "പുഴയ്ക്കൽ",
    "thalikkulam": "തളിക്കുളം",
    "vellangallur": "വെള്ളാങ്ങല്ലൂർ",
    "wadakkanchery": "വടക്കാഞ്ചേരി",

    # Wayanad (WYD)
    "kalpetta": "കൽപ്പറ്റ",
    "mananthavady": "മാനന്തവാടി",
    "panamaram": "പനമരം",
    "sulthan_bathery": "സുൽത്താൻ ബത്തേരി",
}

    updated, missing = 0, []
    for code, ml_name in BLOCK_TRANSLATIONS_ML.items():
        obj, created = Translation.objects.update_or_create(
            category=cat_block, key=code, language=lang_ml,
            defaults={'value': ml_name},
        )
        updated += 1

    print(f"Updated {updated} block translations to Malayalam.")