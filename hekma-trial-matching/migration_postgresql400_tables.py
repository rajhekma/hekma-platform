import os
import sys
import logging
import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv

# LOAD ENV
load_dotenv()

DEV_DB_CONFIG = {
    "host": os.getenv("PG_HOST"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname": os.getenv("PG_DATABASE"),
    "port": os.getenv("PG_PORT", 5432),
}

DEMO_DB_CONFIG = {
    "host": os.getenv("DEMO_PG_HOST"),
    "user": os.getenv("DEMO_PG_USER"),
    "password": os.getenv("DEMO_PG_PASSWORD"),
    "dbname": os.getenv("DEMO_PG_DATABASE"),
    "port": os.getenv("DEMO_PG_PORT", 5432),
}

TABLES = [
    "patient",
    "procedure",
    "observation",
    "medication_order",
    "immunization",
    "encounter",
    "condition",
    "allergy",
    "lab_results"
]

# PATIENT LIST PARSER

RAW_PATIENT_DATA = """
#Oncology

93001ebd-2b3c-4598-45ca-606edc196b49 | Secondary malignant neoplasm of colon
d13a3877-cf08-5736-6a11-eacc5301a556 | Malignant neoplasm of breast (disorder)
1afb4289db22 | Carcinoma in situ of prostate (disorder)
96a88405f843 | Secondary malignant neoplasm of colon
2213188f682c | Metastasis from malignant tumor of prostate (disorder)
517da688b9a5 | Carcinoma in situ of prostate (disorder)
9778bee8-56f3-db86-38fd-ec8f1d2a7161 | Malignant neoplasm of breast (disorder)
f1db3f37c527 | Non-small cell lung cancer (disorder)
51fe876ef2c7 | Overlapping malignant neoplasm of colon
a75f7ee3-6d7c-5bdd-1461-9ffda70e86f3 | Carcinoma in situ of prostate (disorder)
637a1698-8086-287a-f5f9-b0c7e1c6b4d7 | Non-small cell carcinoma of lung
fdb7d4d47875 | Carcinoma in situ of prostate (disorder), Neoplasm of prostate
7f54b091-fae4-1276-3e36-bc7411471d5d | Neoplasm of prostate
3a97fd8fe557 | Non-small cell lung cancer (disorder)
557ff594-735a-4721-877c-427ed81988d1 | Primary malignant neoplasm of colon
7d4b7eaae4d5 | Non-small cell lung cancer (disorder)
4aa3e9934992 | Small cell carcinoma of lung (disorder)
76e8c169181e | Primary small cell malignant neoplasm of lung
dcf5719b8a88 | Metastasis from malignant tumor of prostate (disorder)
bdf28f3c-8c0f-33c5-4f9e-8149e4676050 | Overlapping malignant neoplasm of colon, Malignant neoplasm of breast (disorder)
bc1c07754eb4 | Non-small cell carcinoma of lung
094ab6a2-cdeb-7a38-8991-cb3671d5290f | Primary malignant neoplasm of colon
4a4e561b98fd | Non-small cell carcinoma of lung
d67fb26b-1739-5d2c-c41c-410c03c5f04f | Primary malignant neoplasm of colon
8db5376184ec | Primary small cell malignant neoplasm of lung
17254505755d | Neoplasm of prostate
17b52e9e76fb | Malignant tumor of colon
a0d705a5-8b46-e3fc-0852-c0a77fe77d48 | Malignant neoplasm of breast (disorder)
76a41f9c-4dde-56ff-e4b5-936e075118f6 | Malignant tumor of colon
392f1d96e1a3 | Neoplasm of prostate
1beea36c34e1 | Primary small cell malignant neoplasm of lung
3c6dab905262 | Non-small cell lung cancer (disorder)
a2ad61ddf9ed | Metastasis from malignant tumor of prostate (disorder)
ef38f643dc06 | Carcinoma in situ of prostate (disorder)
71d4e9673780 | Primary malignant neoplasm of colon
483754c3-018f-32ae-96df-cf1151fd4d35 | Metastasis from malignant tumor of prostate (disorder)
69a0d517-1fb6-6a0f-a4c0-a619e4ee1117 | Primary malignant neoplasm of colon
8f764860414a | Small cell carcinoma of lung (disorder)
523b15ed-2adb-7cb1-ad9b-3f5a0453f2ba | Carcinoma in situ of prostate (disorder)
a45f2206-a925-b890-f8f3-f7276089b00f | Non-small cell lung cancer (disorder)
c846b518-80c0-a472-4d2b-1a5c5b5e86c3 | Malignant neoplasm of breast (disorder)
a487a232-f0d3-6607-2342-6b9a95d722ef | Malignant neoplasm of breast (disorder)
40f444f9-e301-c055-b45c-56be0d336a18 | Primary malignant neoplasm of colon
5148555840b2 | Neoplasm of prostate
53e4a94c-920f-6000-6ba0-e4009e7df5ce | Carcinoma in situ of prostate (disorder), Malignant tumor of colon
2a9bc9051647 | Primary small cell malignant neoplasm of lung
4bf19714-7c1a-a3ee-6b2a-3bf263bb4698 | Malignant neoplasm of breast (disorder)
4658db91-0ce8-c479-1999-84c428c9318f | Acute myeloid leukemia, Febrile neutropenia
fe3ee04b-04a6-b752-784f-5b305d220c25 | Acute myeloid leukemia
8d3b8a0d-3b95-7f10-4b47-3ad8a5f48854 | Acute myeloid leukemia
608e2a82-e7c1-7774-7afa-af30cc63d0ee | Acute myeloid leukemia
915f2b9d-5f08-4f6a-e2fa-3b75f201807e | Acute myeloid leukemia
1c7467d8-6abb-dca3-61e8-015482822cb2 | Acute myeloid leukemia
36785760-2fc0-91f1-8923-2568330d1838 | Acute myeloid leukemia
602645c0-4bb0-e207-37b1-b6f2fb53ee83 | Acute myeloid leukemia
a564ec1d-5c18-89c8-f01f-db50e14cb3e7 | Acute myeloid leukemia
c2d07a7d-4134-b5eb-2d96-bc80fdbdf436 | Acute myeloid leukemia
52545cb3-e7d2-0726-a4e4-6eec6a425f27 | Acute myeloid leukemia
4292ea18-874c-61c0-01cd-9869e5c571cf | Acute myeloid leukemia
bfbd6001-af86-2901-b5b3-3244058b4367 | Acute myeloid leukemia
168d8ace-6b94-aaef-ce26-461a70835b80 | Acute myeloid leukemia
0329bce0-ffd9-42c7-168d-69bb68aa0715 | Acute myeloid leukemia
42947dcd-6fc1-f546-38b2-a148a290ccc1 | Acute myeloid leukemia
fb06557e-ff90-99a6-f6a0-5a6ecbbf9b84 | Acute myeloid leukemia
97efe5ba-92f7-a2d2-f108-dd2888d69132 | Acute myeloid leukemia
56a6df83-83d0-6935-757d-4560086e9fd1 | Acute myeloid leukemia
27dab265-32c4-0f34-28bb-81e9fe660536 | Acute myeloid leukemia
e2dce2ec-2712-ad61-ddc8-afb9829ff296 | Acute myeloid leukemia
13f84e83-6201-3249-61f9-2c1ed48e5df7 | Acute myeloid leukemia
a56ddab0-1c26-4c91-6493-c17715f127d5 | Acute myeloid leukemia
22dade73-d0d0-8aa0-ced6-d84fa6951aa8 | Acute myeloid leukemia
2620e523-568c-13a6-16d0-c84f593f88b6 | Acute myeloid leukemia
011e1069-146a-6768-155b-37cfa948f386 | Acute myeloid leukemia
0192ef47-5fee-4f98-9a04-f2c6fb80e214 | Acute myeloid leukemia
9b67a2f7-694e-e7e5-4e41-e2d33a0d0178 | Acute myeloid leukemia, Bacteremia
96d82701-a639-7014-7037-c52100441294 | Acute myeloid leukemia, Febrile neutropenia
bdadcb4f-d98c-e409-4235-e6d4848b3067 | Acute myeloid leukemia
a6fa4ca2-4263-c0c0-fce8-96633cc4ea55 | Acute myeloid leukemia
691965f3-97a8-cb87-3192-feb5f3a36bc7 | Acute myeloid leukemia
96b37959-0352-d6db-526c-bfbbf1d05b14 | Acute myeloid leukemia
a2a0b3c6-19e9-bb36-2948-fb7e099ac7d9 | Acute myeloid leukemia
15451d10-8541-3bd2-ef6c-86de7e5564e7 | Acute myeloid leukemia, Febrile neutropenia
f5f910e0-69ac-5455-07cc-90bb2c3982f3 | Acute myeloid leukemia
c3661e59-7436-fcfd-e29f-63ba82902736 | Acute myeloid leukemia, Febrile neutropenia
020fabda-45a1-358f-ce3d-c75ba5052271 | Acute myeloid leukemia, Febrile neutropenia
34b23986-fb33-4110-a9f6-6a1a5c3acc76 | Acute myeloid leukemia, Febrile neutropenia
55a30868-69b6-1c6e-50fd-cdc8198cc587 | Acute myeloid leukemia
ee8a05b6-8e1a-abb6-71dd-e3c3e31e0b97 | Acute myeloid leukemia
59ea4462-5e81-8234-7d8e-819b4e28f260 | Acute myeloid leukemia
64d9711a-fe99-2e5c-aeb9-8372fccb7cf3 | Acute myeloid leukemia
abd036c6-2589-5867-9880-a80af094f388 | Acute myeloid leukemia
5e318658-a938-1826-7c85-b946ab96c5e5 | Acute myeloid leukemia
c7519cf7-214b-98a6-7546-e40ccaf44d99 | Acute myeloid leukemia
20407a3e-d63c-d43f-a640-7de51dac79a5 | Acute myeloid leukemia
6cdb8798-badc-44b4-1649-d6a5824de56d | Acute myeloid leukemia
835f6b15-0dae-f5ff-9df0-4fd422a9bcbd | Acute myeloid leukemia
381e78e4-e506-5371-0dc3-b34579a5a4f2 | Acute myeloid leukemia


#Cardiology


412e8ae98691 | Cardiac Arrest
9033b4776551 | Myocardial Infarction
4b3471e1bbad | Coronary Heart Disease
f62ceafe-e6f6-dab7-2108-7ae3b04fbd44 | Cardiac Arrest
31982b0c-868b-294a-ef8a-830e2a77ca4f | Coronary Heart Disease
b6574e62-14c5-d268-f9a7-21514628af36 | History of myocardial infarction
1d939a5bf18c | Coronary Heart Disease
3741801e0ba3 | Cardiac Arrest
5587387235be | History of myocardial infarction
fbf968f2-d58c-8516-c31c-e9c0d09758a9 | History of myocardial infarction
0f6200e3-c500-577e-7990-941548e646e7 | Acute deep venous thrombosis
5eaa789d601e | Myocardial Infarction
0ef0222c-a1b8-48e4-af4a-8ab3658fdb80 | Coronary Heart Disease
c63a3920-92cc-3dfb-7fdb-29e9038e92b3 | Acute deep venous thrombosis
93f52bee4e26 | Myocardial Infarction
508d8e09-7e1f-0a8d-3313-dfe635097015 | Coronary Heart Disease
e3aaacc7-44d6-912a-85fb-9092fadcfb7d | Chronic congestive heart failure
8c5eed34-228e-df52-7faf-55111d1cfecf | History of myocardial infarction
0a8d5cc7-2370-9fbc-cc05-0c53dcfd15a0 | Chronic congestive heart failure
3f2ce69dfbf3 | Myocardial Infarction
afe6cc7a-e3ce-79f2-0076-1a5a4cb42ae6 | Myocardial Infarction
63a43ee8-0c16-7cd1-cd5f-d210071678ba | Coronary Heart Disease
5766ca53-2af1-60c1-bee2-ee4fed3824b3 | Chronic congestive heart failure
8a60cfe8-1bf0-5c4d-bbe1-2438da3d122e | Cardiac Arrest
0d1ef4886767 | Myocardial Infarction
b4dbc3d0-e4cd-238a-6fbe-3b39eba76532 | Myocardial Infarction
178a6ce2-1a2f-3795-6c23-ba30edfec301 | Chronic congestive heart failure
5c3efc64-62e6-9dc4-810c-234c2e7864ca | Chronic congestive heart failure
3885f1f11fc8 | History of myocardial infarction
e09e826c-e463-1fbd-20d4-cff9e9059a01 | Cardiac Arrest
ca0dc3fe-3be4-659d-6129-f56709aa6bf4 | Cardiac Arrest
3a7a83bf0200 | Cardiac Arrest
9f7fd9e1-34b1-7368-1175-0e4fd748306f | Chronic congestive heart failure
ec0c64f7-6251-16dd-84fb-20b84be650c2 | Myocardial Infarction
11f50dd59d91 | Pulmonary heart disease, Diphtheritic cardiomyopathy
a6d6ed015bf8 | Cardiomyopathy, Pericardial effusion
3d3d15496c25 | Atherosclerosis of coronary artery bypass graft, Chronic thromboembolic pulmonary hypertension
38958816-a679-4c64-baa1-d7525ae0b66d | Cardiac arrest history
9e72e40b7b06 | Heart and renal disease


#diabetic/Metabolic


5e2aad44-63e8-4a62-dc58-6e8b456178de | Diabetic neuropathy
3759dd81-6dea-4406-4327-d0f105dcc984 | Diabetic neuropathy
6902a9b9-fc5b-aa69-72da-3c2b5b77d324 | Proliferative diabetic retinopathy
a3b38de910dd | Diabetic retinopathy with macular edema
83be0581-9620-002a-558f-213e26f32282 | Diabetic retinopathy with macular edema
a394042c7d48 | Proliferative diabetic retinopathy
40f8dd83-cec4-641f-44df-d95ed5ae19af | Proliferative diabetic retinopathy
566bf777-3b5b-fa5b-25bb-050af10cb56d | Proliferative diabetic retinopathy
05a361edffbc | Nonproliferative diabetic retinopathy
08f32835-4c82-9144-7aec-db681d96ac94 | Diabetic retinopathy
61834831-09ee-f0c7-a678-5ebbc3486224 | Diabetic retinopathy with macular edema
946b74ef-6beb-0219-2a7c-ca22b83208e1 | Diabetic retinopathy with macular edema
2aab16db-45a8-3653-1277-8536e3b6e76c | Diabetic retinopathy
653299ae-c489-669b-e794-37f668da7ec5 | Diabetes with blindness
c842dbfc816b | Diabetic proteinuria
282c532e-e546-1a5f-d6fa-0dd4444cbea1 | Diabetic retinopathy with macular edema
157e4f5a-cdbe-53e2-19e0-a42da8e41eed | Diabetic proteinuria
ee52f335a401 | Diabetic retinopathy with CKD
baeb07ee-da87-470c-abc7-64670b896593 | Diabetic proteinuria
fd2997b5-80d7-2e75-d226-de7aa19f9b08 | Diabetic retinopathy
e45e75c9-04f2-e85f-b5c8-09c4097bbba0 | Proliferative diabetic retinopathy
21d896d9314a | Advanced diabetic retinopathy
25ca2651f2cc | Diabetic neuropathy
6a104967-e15f-c300-86a1-b66eec212008 | Diabetic proteinuria
f62f7c2e-5ee1-322d-b533-c18309b18755 | Diabetic proteinuria
028d4281-2a45-167c-a82e-5f3e67b9aef7 | Diabetic retinopathy with macular edema
3304e8bb783c | Type 2 diabetes mellitus
41ff2148-485e-208f-8a26-03ba8a3370d0 | Diabetic retinopathy
b11d62f4-82ba-b9c0-c303-28817f4db0b6 | Diabetic proteinuria
15ce80e7-0bd8-2831-ac33-d6623d833949 | Diabetic retinopathy with macular edema
4acd110f-b52c-dac8-894e-2570303e05ae | Diabetic neuropathy
2fe737d3-9c21-4ec6-224f-668bf064fe09 | Diabetic retinopathy
830417f3-e42d-c055-1f99-c002eb90a1e9 | Diabetic retinopathy with macular edema
6161831c-1d73-891c-de97-0a0ba6e274dd | Type 2 diabetes with retinopathy
e467f71f186f | Type 2 diabetes with angiopathy
75d7dff9-7898-da40-a6f4-e45a2823b23d | Diabetes with obesity
7080bc2c-3898-f497-47ae-5779c08fc012 | Diabetes with metabolic syndrome
e4d9445d-b20e-b3fd-b02f-6d0223f37bb9 | Diabetes with metabolic complications
64d9711a-fe99-2e5c-aeb9-8372fccb7cf3 | Diabetes with CKD
835f6b15-0dae-f5ff-9df0-4fd422a9bcbd | Diabetes with hyperlipidemia
6bae15bd-b937-57e6-2a8f-124d886155ed | Diabetes with metabolic syndrome
63b3047d-36e8-c1ee-bf73-bbf5bee7a990 | Diabetes with systemic complication
616639be-8c23-6052-224b-fd27e66b8af0 | Diabetes with metabolic disorder
c59b0de7-9814-688b-c9e5-087c65d79133 | Diabetes with metabolic + sleep disorder
b9a8cbdf-e2ba-9151-87a3-5c5d87ba76f0 | Diabetes with complication
f2f1f086-8b77-780b-7334-4d09c28e745e | Diabetes with inflammatory condition
8b45087c-3d9b-5149-a9ce-d3908db79603 | Prediabetes with metabolic syndrome
92e37520-c8d3-ca3e-538a-7c9a7d22b5f7 | Prediabetes with metabolic risk
e6060764-2980-087f-3c0d-730e1c658b99 | Prediabetes with metabolic + social stress
cd50c213-37db-417a-4336-73940d2206ef | Diabetes with metabolic syndrome
95df8f32-70d0-7502-4f80-c6a485385a02 | Diabetes with infection and metabolic stress

#respiratory

4cb2d379-a03c-8edc-f41a-59b049be3c27 | Acute pulmonary embolism
43c86312-475e-82fe-ea59-8e29f0230cce | Pulmonary emphysema
2598dc0b-4577-b5bd-2952-c47bf32c98a0 | Acute respiratory distress syndrome
4d35f68e-8cf4-0a51-5eb6-0ea8415cf2f0 | Pulmonary emphysema
58b54c1a-1bea-b050-2b25-f5f1cd85211f | Pulmonary emphysema
46dad794-bfa9-57cf-09dd-e2282faeab34 | Acute pulmonary embolism
8d4502e0-67c0-96c7-d4ba-d2f3209563d8 | Acute pulmonary embolism
c1ced486-307b-bb08-b574-384928db1618 | Pulmonary emphysema
72ff09f0b251 | Chronic obstructive bronchitis
fc099384-00eb-08eb-2a6a-e0ba0cd14c5f | Acute respiratory distress syndrome
dcaebd6d2a5f | Pneumonia
0bec29b7-1e82-0090-d4c1-1c0b805be110 | Chronic obstructive bronchitis
127134d04186 | Pneumonia
e52adcd0-d560-f71e-be0f-ff43b0b4cfef | Acute respiratory distress syndrome
10432f1a264a | Pneumonia
b65b2ca8-6b8f-21dc-c81a-0197ab37a648 | Acute pulmonary embolism
fdb0439c-9c99-3146-e001-c3a1052c61b0 | Cystic fibrosis
fd491efe-98f9-c797-f664-535c4c60fec6 | Pulmonary emphysema
26df3100a966 | Pneumonia
96e4384f-a384-bc8b-8f9f-fa71e1a1e678 | Acute respiratory distress syndrome
3f5956e6-222c-67fa-2cbd-8b17a3d15bb3 | Acute respiratory distress syndrome
257df210-cf5f-db23-251f-919a8515f2e4 | Pulmonary emphysema
cbb8ebc93a2f | Chronic obstructive bronchitis
ac819117-a8a7-ae63-acde-4833bba99410 | Acute respiratory distress syndrome
6ea33d49-cce2-b8e0-5667-3e2b61f8ea8e | Pulmonary emphysema
693b8fad-4346-67cf-181b-ac767dd3112d | Sleep apnea
98815040-90a7-0bc4-0471-56efb4c7bd49 | Sleep apnea
06deecf3-32c0-9d59-7a3b-6c7424416594 | Sleep apnea
e1506725-87fb-7982-31fc-6492d17804d3 | Acute respiratory distress syndrome
f5a02229-e916-0e51-a883-40fcc5c01d06 | Pulmonary emphysema
fcda5f2c-3116-da1f-59a5-4a9531656648 | Sleep apnea
9d42b616a404 | Cystic fibrosis
7abb2b4a-623a-6dc0-b77a-fde172150655 | Acute respiratory distress syndrome
576b34cec2e0 | Pneumonia
8f352318-5d58-13dd-f8c1-6e6c954a0af6 | Pulmonary embolism
b9c3e2d5-0afa-1643-077b-e63f7d9e4348 | Chronic obstructive bronchitis
61dc045c-db6f-98b1-3644-63a4903948f6 | Sleep apnea
83d43089-da6c-c947-ada8-c9a6ea5853d7 | Hypoxemia
e4297178b65c | Chronic obstructive pulmonary disease with acute bronchitis
3837b17f4d8f | Chronic obstructive pulmonary disease
6573114b-2ccf-dcfd-409f-d4a13d805ea6 | Chronic obstructive bronchitis
3ae7af172a6c | Chronic obstructive bronchitis
0b07b148-e8cb-ed76-e31a-937b32ea20c2 | Hypoxemia
e621c543-a829-4524-ef43-f515441f0565 | Respiratory muscle dysfunction
64bee596-de5a-47c4-c4e9-21f6b247ab36 | Hypoxemia
2c6f9856-4572-eda6-62c5-82e82723f617 | Pneumonia
39af53ab-b477-5db7-4d17-555c0e605818 | Respiratory infection

#Neurology

80449819-9174-055a-d596-340e0845bb60 | Cerebral palsy
af15ed57-99dc-14c4-a06e-319e70007bd4 | Spinal cord injury with paralysis
a577f362-4bc6-f286-e91e-b8651916382e | Traumatic brain injury
c2670033-a3bc-5b90-5a09-dd73a6e67274 | Traumatic brain injury
ba31956c-076e-4c52-03b7-56a21a477598 | Chronic migraine
1c04424e-0292-44c3-6fd9-578f712052cf | Chronic migraine
7bbaa467-4fdd-49f3-e481-c1e19efb9014 | Traumatic brain injury
30b79a3090dd | Alzheimer's disease
22c42a6a-2abb-91f5-ebd6-20a62b22bc7f | Epilepsy
bd4b966d-b754-31be-c725-d10795b4502a | Early onset Alzheimer's
42adfdba-b700-c39a-d4c2-268cf94336ac | Stroke
76dedcf9-2731-49d8-c42f-c1a6471832d1 | Traumatic brain injury
cd0cc177-6cfb-05a2-9bb2-9ea1ae7ae660 | Concussion brain injury
487977840743 | Alzheimer's disease
2a30e9a4-8ef9-25b4-3b1c-7ca90f7e9ee5 | Chronic migraine
75f29f46-2724-b501-137a-99c27924c472 | Dystonia
4888bea8-529a-6ac6-7dc9-f66a0afa9616 | Cerebral palsy
0ad39c55-8cd7-384e-3e85-0a4196e72839 | Traumatic brain injury
e65fa8c7-6c97-5935-e0a1-28d2029dfe9e | ADHD with migraine
0949be73-cd1e-df84-b259-ff1f8ec0a177 | Intellectual disability
6b968907-31d2-78bd-a169-3cdd70fa97b4 | Spinal cord injury
c3a741e4-8bdf-969f-5dad-b8f3e9104414 | Traumatic brain injury
1a5e27b04c4d | Epilepsy
14bb5f6d-7c90-190c-f639-3e157ae8ff68 | Intellectual disability with cerebral palsy
b7c94111-cce0-b680-efe7-bf3388bfaf09 | Dystonia
005c41a44333 | Stroke
12143528-3854-eb29-3216-e113ef10dc35 | Meningocele
69fb90d17e6d | Seizure disorder
5e0dab06-f74b-b2cf-1373-fc9dd2e8dbe1 | Chronic migraine
8c2c3b15-4c4c-1737-2206-085156f5c1de | Traumatic brain injury
bcf362b1-5a42-2bea-e5a2-732c267d83dd | Early Alzheimer’s
5e1b7ced-95bd-4ac3-65cb-ef9282fd7b09 | Spina bifida
ef02027b-38c3-4337-062a-3b845980b0b0 | Epilepsy
7affc1979b8e | Alzheimer's disease
30ae755d-7a28-7df4-d556-fbaa55e40881 | Intellectual disability
f98926f0be94 | Early Alzheimer’s
0e900e30-95e9-ca2c-960e-2600bb793507 | Spasticity with cerebral palsy
cc8c76b5-d44d-5c8f-fa08-e6f040af8e7d | Epilepsy
a6366105-07bb-2a63-1f51-2f88f4e08979 | Spasticity
a0d72e51-d0c7-006a-7350-60e796ef31e5 | Hydrocephalus
7f153144-748f-1eea-da10-bac4a4f01430 | Epilepsy
9b42b07c-a8c9-8ffd-8c2f-6c17ea514ac0 | Chronic migraine
e34a58c8-58bd-77af-1c07-1a6167304dd9 | Epilepsy
53b93708-5ff2-14e8-7bb0-765c5210ec94 | Epilepsy
ed2fa2b8-177d-c4b5-06d4-675f5aec1e13 | Spasticity
517b90c993ae | Seizure history
2ce5a5e5a61c | Alzheimer's disease
ed448d7a-b197-4100-072b-aa9302a1e9d5 | Epilepsy
f321c1cc-30b2-d7f4-e091-b2baa50b32d3 | Seizure history
07aca37a-2cfe-5c19-bf0d-fb2620f4b7a0 | Intellectual disability
b06cb508-6f48-b690-32a0-bf82ae653831 | Chronic migraine
953aa924-8b5d-83a6-3a84-016e7b36dca0 | Chronic migraine
c1322124-a0ed-6b2b-5683-2cc00a7459b0 | Intellectual disability
3085bbf8-4f96-22ef-b803-d0c8a46cf841 | Intellectual disability
a9ba6af8-ba09-7f1e-8b18-19f17a24ed23 | Epilepsy
6cbbc87c-2dec-5aa7-5445-de757224438f | Epilepsy
8d5c1930-a905-973a-0738-7851d35da905 | Cerebral palsy
6acac20139b7 | Traumatic brain injury
6ec325dd-5da0-1a75-6754-07a33a436e36 | Spina bifida
f03ad512-f068-0c8b-b4a3-cf25208983f0 | Chronic migraine
fa804e75-b53b-3e60-3afb-e9ff3a13b0c7 | Cerebral palsy
4e70791a-6175-ff52-e9c3-7529ede9b9a9 | Intellectual disability
3f63216d-d172-60f2-7479-c9e66609d2d0 | Early Alzheimer’s
d29b8e57a9de | Stroke
94942af84ba6 | Alzheimer's disease
4fb486b2-b036-cf31-f35e-d5065788115f | Epilepsy with intellectual disability
34965643-9a8d-ec28-6ccb-bf2a2655df32 | Chronic migraine
461a59608cbd | Neuropathy with neurological disorder
625228522cc8 | Anoxic brain damage"""

def extract_patient_ids():
    ids = []
    for line in RAW_PATIENT_DATA.splitlines():
        if "|" in line:
            pid = line.split("|")[0].strip()
            if pid:
                ids.append(pid)
    return list(set(ids))

PATIENT_IDS = extract_patient_ids()

# LOGGING

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# VALIDATION

def validate_config():
    required = [
        "PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE",
        "DEMO_PG_HOST", "DEMO_PG_USER", "DEMO_PG_PASSWORD", "DEMO_PG_DATABASE"
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        log.error(f"Missing env variables: {missing}")
        sys.exit(1)

# FETCH DATA

def fetch_data(table, patient_ids):
    conn = psycopg2.connect(**DEV_DB_CONFIG)
    cursor = conn.cursor()

    if table == "patient":
        query = f"""
            SELECT * FROM public.{table}
            WHERE id = ANY(%s)
        """
    else:
        query = f"""
            SELECT * FROM public.{table}
            WHERE patient_id = ANY(%s)
        """

    cursor.execute(query, (patient_ids,))
    columns = [desc[0] for desc in cursor.description]

    log.info(f"{table}: fetching data...")

    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        yield rows, columns

    cursor.close()
    conn.close()

# CONVERT JSONB

def convert_row(row):
    new_row = []
    for val in row:
        if isinstance(val, (dict, list)):
            new_row.append(Json(val))
        else:
            new_row.append(val)
    return tuple(new_row)

# DROP INDEXES (DEMO DB )

def drop_indexes(conn, table):
    cursor = conn.cursor()

    index_map = {
        "procedure": ["idx_procedure_raw_resource"],
        "observation": ["idx_observation_raw_resource"],
        "condition": ["idx_condition_raw_resource"],
        "allergy": ["idx_allergy_raw_resource"],
        "lab_results": ["idx_lab_results_raw_resource"],
        "immunization": ["idx_immunization_raw_resource"],
        "medication_order": ["idx_medication_raw_resource"],
        "encounter": ["idx_encounter_raw_resource"],
    }

    indexes = index_map.get(table, [])

    for idx in indexes:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {idx}")
            log.info(f"{table}: dropped index {idx}")
        except Exception as e:
            log.warning(f"{table}: failed to drop {idx} → {e}")

    conn.commit()
    cursor.close()

# RECREATE INDEXES

def recreate_indexes(conn, table):
    cursor = conn.cursor()

    index_queries = {
        "procedure": [
            "CREATE INDEX idx_procedure_raw_resource ON procedure USING gin (raw_resource)"
        ],
        "observation": [
            "CREATE INDEX idx_observation_raw_resource ON observation USING gin (raw_resource)"
        ],
        "condition": [
            "CREATE INDEX idx_condition_raw_resource ON condition USING gin (raw_resource)"
        ],
        "allergy": [
            "CREATE INDEX idx_allergy_raw_resource ON allergy USING gin (raw_resource)"
        ],
        "lab_results": [
            "CREATE INDEX idx_lab_results_raw_resource ON lab_results USING gin (raw_resource)"
        ],
        "immunization": [
            "CREATE INDEX idx_immunization_raw_resource ON immunization USING gin (raw_resource)"
        ],
        "medication_order": [
            "CREATE INDEX idx_medication_raw_resource ON medication_order USING gin (raw_resource)"
        ],
        "encounter": [
            "CREATE INDEX idx_encounter_raw_resource ON encounter USING gin (raw_resource)",
            "CREATE INDEX idx_encounter_patient ON encounter(patient_id)"
        ],    }

    queries = index_queries.get(table, [])

    for q in queries:
        try:
            cursor.execute(q)
            log.info(f"{table}: recreated index")
        except Exception as e:
            log.warning(f"{table}: failed to recreate index → {e}")

    conn.commit()
    cursor.close()

# INSERT DATA 

def insert_data(table, data_generator):
    conn = psycopg2.connect(**DEMO_DB_CONFIG)
    cursor = conn.cursor()

    success = 0
    skipped = 0

    # DROP INDEXES BEFORE INSERT
    drop_indexes(conn, table)

    try:
        for rows, columns in data_generator:

            col_names = ", ".join(columns)
            clean_rows = [convert_row(row) for row in rows]

            execute_values(
                cursor,
                f"""
                INSERT INTO public.{table} ({col_names})
                VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                clean_rows,
                page_size=1000
            )

            success += len(clean_rows)

            conn.commit()

            log.info(f"{table}: progress → inserted={success}, skipped={skipped}")

    except Exception as e:
        conn.rollback()
        log.error(f"{table}: fatal error → {e}")
        sys.exit(1)

    finally:
        # RECREATE INDEXES AFTER INSERT
        recreate_indexes(conn, table)

        cursor.close()
        conn.close()

    log.info(f"{table}: completed → inserted={success}, skipped={skipped}")

# MAIN

def main():
    validate_config()

    log.info(f"Total unique patient IDs: {len(PATIENT_IDS)}")

    for table in TABLES:
        log.info(f"--- Processing table: {table} ---")
        data_gen = fetch_data(table, PATIENT_IDS)
        insert_data(table, data_gen)

    log.info(" Full PostgreSQL migration completed successfully!")


if __name__ == "__main__":
    main()