# CATEGORY KEYWORDS

DISEASE_CATEGORY_MAP = {

    "oncology": [
        "cancer", "tumor", "tumour", "carcinoma",
        "sarcoma", "leukemia", "lymphoma",
        "melanoma", "neoplasm", "malignancy",
        "metastasis", "oncology"
    ],

    "hematology": [
        "anemia", "haemophilia", "hemophilia",
        "blood disorder", "platelet", "clotting",
        "thrombosis", "bleeding disorder"
    ],

    "cardiovascular": [
        "hypertension", "heart", "cardio",
        "stroke", "artery", "vascular",
        "coronary", "myocardial", "cardiac",
        "arrhythmia"
    ],

    "neurology": [
        "alzheimer", "parkinson", "epilepsy",
        "brain", "neuro", "multiple sclerosis",
        "neuropathy", "seizure", "dementia"
    ],

    "psychiatry": [
        "depression", "anxiety", "bipolar",
        "schizophrenia", "mental disorder",
        "psychiatric", "panic disorder"
    ],

    "infectious diseases": [
        "covid", "hiv", "infection",
        "tuberculosis", "virus", "viral",
        "bacterial", "fungal", "sepsis"
    ],

    "immunology": [
        "autoimmune", "immune disorder",
        "allergy", "immune deficiency",
        "lupus", "immune system"
    ],

    "endocrinology": [
        "thyroid", "hormone", "pituitary",
        "endocrine", "adrenal"
    ],

    "metabolic disorders": [
        "diabetes", "obesity", "metabolic",
        "insulin", "hyperglycemia",
        "hypoglycemia", "lipid disorder"
    ],

    "gastroenterology": [
        "gastritis", "ulcer", "stomach",
        "intestinal", "colitis", "ibs",
        "crohn", "digestive"
    ],

    "hepatology": [
        "liver", "hepatitis", "cirrhosis",
        "fatty liver", "hepatic"
    ],

    "nephrology": [
        "kidney", "renal", "nephro",
        "dialysis", "chronic kidney"
    ],

    "respiratory": [
        "asthma", "copd", "bronchitis",
        "lung disease", "pulmonary",
        "respiratory", "pneumonia"
    ],

    "dermatology": [
        "skin", "eczema", "psoriasis",
        "dermatitis", "acne", "rash"
    ],

    "rheumatology": [
        "arthritis", "rheumatoid",
        "joint inflammation", "lupus"
    ],

    "musculoskeletal": [
        "bone", "fracture", "muscle",
        "orthopedic", "skeletal"
    ],

    "ophthalmology": [
        "eye", "vision", "glaucoma",
        "cataract", "retina"
    ],

    "otolaryngology": [
        "ear", "nose", "throat",
        "sinus", "ent"
    ],

    "urology": [
        "urinary", "prostate",
        "bladder", "urology"
    ],

    "obstetrics": [
        "pregnancy", "maternal",
        "antenatal", "gestation"
    ],

    "reproductive": [
        "fertility", "infertility",
        "reproductive", "ovarian",
        "testicular"
    ],

    "pediatrics": [
        "child", "pediatric",
        "infant", "newborn"
    ],

    "geriatrics": [
        "elderly", "aging",
        "geriatric"
    ]
}


# PRIORITY ORDER 

PRIORITY_ORDER = [
    "oncology",                # cancer should override everything
    "hematology",
    "cardiovascular",

    "metabolic disorders",     # diabetes before neurology
    "endocrinology",

    "neurology",
    "psychiatry",
    "infectious diseases",
    "immunology",
    "gastroenterology",
    "hepatology",
    "nephrology",
    "respiratory",
    "dermatology",
    "rheumatology",
    "musculoskeletal",
    "ophthalmology",
    "otolaryngology",
    "urology",
    "obstetrics",
    "reproductive",
    "pediatrics",
    "geriatrics"
]


# UI CONFIG

CATEGORY_UI_MAP = {
    "oncology": {"icon": "oncology", "color": "#E11D48", "bgColor": "#FDE2E7"},
    "hematology": {"icon": "hematology", "color": "#DC2626", "bgColor": "#FEE2E2"},
    "cardiovascular": {"icon": "heart", "color": "#EC4899", "bgColor": "#FCE7F3"},
    "neurology": {"icon": "brain", "color": "#7C3AED", "bgColor": "#EDE9FE"},
    "psychiatry": {"icon": "psychiatry", "color": "#6366F1", "bgColor": "#E0E7FF"},
    "infectious diseases": {"icon": "virus", "color": "#10B981", "bgColor": "#D1FAE5"},
    "immunology": {"icon": "immunology", "color": "#14B8A6", "bgColor": "#CCFBF1"},
    "endocrinology": {"icon": "endocrinology", "color": "#F97316", "bgColor": "#FFEDD5"},
    "metabolic disorders": {"icon": "metabolic", "color": "#F59E0B", "bgColor": "#FEF3C7"},
    "gastroenterology": {"icon": "gastro", "color": "#22C55E", "bgColor": "#DCFCE7"},
    "hepatology": {"icon": "liver", "color": "#84CC16", "bgColor": "#ECFCCB"},
    "nephrology": {"icon": "kidney", "color": "#06B6D4", "bgColor": "#CFFAFE"},
    "respiratory": {"icon": "respiratory", "color": "#0EA5E9", "bgColor": "#E0F2FE"},
    "dermatology": {"icon": "skin", "color": "#3B82F6", "bgColor": "#DBEAFE"},
    "rheumatology": {"icon": "joint", "color": "#D946EF", "bgColor": "#FAE8FF"},
    "musculoskeletal": {"icon": "bone", "color": "#6B7280", "bgColor": "#F3F4F6"},
    "ophthalmology": {"icon": "eye", "color": "#8B5CF6", "bgColor": "#F3E8FF"},
    "otolaryngology": {"icon": "ent", "color": "#A855F7", "bgColor": "#F5E8FF"},
    "urology": {"icon": "urology", "color": "#2563EB", "bgColor": "#DBEAFE"},
    "obstetrics": {"icon": "pregnancy", "color": "#EC4899", "bgColor": "#FCE7F3"},
    "reproductive": {"icon": "reproductive", "color": "#F43F5E", "bgColor": "#FFE4E6"},
    "pediatrics": {"icon": "child", "color": "#0EA5E9", "bgColor": "#E0F2FE"},
    "geriatrics": {"icon": "elderly", "color": "#9CA3AF", "bgColor": "#F3F4F6"},
    "default": {"icon": "general", "color": "#6B7280", "bgColor": "#F3F4F6"}
}



def map_disease_to_ui(disease_name: str):

    if not disease_name:
        return build_ui_response(disease_name, "default")

    disease_lower = disease_name.lower()

    for category in PRIORITY_ORDER:
        keywords = DISEASE_CATEGORY_MAP.get(category, [])

        for keyword in keywords:
            if keyword in disease_lower:
                return build_ui_response(disease_name, category)

    return build_ui_response(disease_name, "default")


# RESPONSE BUILDER

def build_ui_response(disease_name, category):
    ui = CATEGORY_UI_MAP.get(category, CATEGORY_UI_MAP["default"])

    return {
        "name": disease_name,
        "category": category,
        "icon": ui["icon"],
        "color": ui["color"],
        "bgColor": ui["bgColor"]
    }