from django.db import models


class IndianState(models.TextChoices):
    ANDAMAN_AND_NICOBAR_ISLANDS = (
        "AN",
        "Andaman and Nicobar Islands",
    )
    ANDHRA_PRADESH = "AP", "Andhra Pradesh"
    ARUNACHAL_PRADESH = "AR", "Arunachal Pradesh"
    ASSAM = "AS", "Assam"
    BIHAR = "BR", "Bihar"
    CHANDIGARH = "CH", "Chandigarh"
    CHHATTISGARH = "CG", "Chhattisgarh"
    DADRA_NAGAR_HAVELI_DAMAN_DIU = (
        "DH",
        "Dadra and Nagar Haveli and Daman and Diu",
    )
    DELHI = "DL", "Delhi"
    GOA = "GA", "Goa"
    GUJARAT = "GJ", "Gujarat"
    HARYANA = "HR", "Haryana"
    HIMACHAL_PRADESH = "HP", "Himachal Pradesh"
    JAMMU_AND_KASHMIR = "JK", "Jammu and Kashmir"
    JHARKHAND = "JH", "Jharkhand"
    KARNATAKA = "KA", "Karnataka"
    KERALA = "KL", "Kerala"
    LADAKH = "LA", "Ladakh"
    LAKSHADWEEP = "LD", "Lakshadweep"
    MADHYA_PRADESH = "MP", "Madhya Pradesh"
    MAHARASHTRA = "MH", "Maharashtra"
    MANIPUR = "MN", "Manipur"
    MEGHALAYA = "ML", "Meghalaya"
    MIZORAM = "MZ", "Mizoram"
    NAGALAND = "NL", "Nagaland"
    ODISHA = "OD", "Odisha"
    PUDUCHERRY = "PY", "Puducherry"
    PUNJAB = "PB", "Punjab"
    RAJASTHAN = "RJ", "Rajasthan"
    SIKKIM = "SK", "Sikkim"
    TAMIL_NADU = "TN", "Tamil Nadu"
    TELANGANA = "TS", "Telangana"
    TRIPURA = "TR", "Tripura"
    UTTAR_PRADESH = "UP", "Uttar Pradesh"
    UTTARAKHAND = "UK", "Uttarakhand"
    WEST_BENGAL = "WB", "West Bengal"
