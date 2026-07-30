CATALOGUE_MANAGER = "Catalogue Manager"
INVENTORY_MANAGER = "Inventory Manager"
PRESCRIPTION_REVIEWER = "Prescription Reviewer"
ORDER_MANAGER = "Order Manager"
ACCOUNTS_MANAGER = "Accounts Manager"


STAFF_GROUP_NAMES = (
    CATALOGUE_MANAGER,
    INVENTORY_MANAGER,
    PRESCRIPTION_REVIEWER,
    ORDER_MANAGER,
    ACCOUNTS_MANAGER,
)


STAFF_GROUP_PERMISSIONS = {
    CATALOGUE_MANAGER: (
        ("catalog", "view_brand"),
        ("catalog", "add_brand"),
        ("catalog", "change_brand"),
        ("catalog", "view_category"),
        ("catalog", "add_category"),
        ("catalog", "change_category"),
        ("catalog", "view_colour"),
        ("catalog", "add_colour"),
        ("catalog", "change_colour"),
        ("catalog", "view_material"),
        ("catalog", "add_material"),
        ("catalog", "change_material"),
        ("catalog", "view_frameshape"),
        ("catalog", "add_frameshape"),
        ("catalog", "change_frameshape"),
        ("catalog", "view_frametype"),
        ("catalog", "add_frametype"),
        ("catalog", "change_frametype"),
        ("catalog", "view_productdesign"),
        ("catalog", "add_productdesign"),
        ("catalog", "change_productdesign"),
        ("catalog", "view_productvariant"),
        ("catalog", "add_productvariant"),
        ("catalog", "change_productvariant"),
        ("catalog", "view_productoffer"),
        ("catalog", "add_productoffer"),
        ("catalog", "change_productoffer"),
        ("catalog", "view_productimage"),
        ("catalog", "add_productimage"),
        ("catalog", "change_productimage"),
    ),
    INVENTORY_MANAGER: (),
    PRESCRIPTION_REVIEWER: (
        ("accounts", "view_user"),
        ("prescriptions", "view_prescription"),
        ("prescriptions", "change_prescription"),
        ("prescriptions", "review_prescription"),
        ("prescriptions", "view_prescriptioneyevalue"),
        ("prescriptions", "add_prescriptioneyevalue"),
        ("prescriptions", "change_prescriptioneyevalue"),
    ),
    ORDER_MANAGER: (
        ("locations", "view_address"),
        ("locations", "view_serviceablepincode"),
        ("locations", "add_serviceablepincode"),
        ("locations", "change_serviceablepincode"),
    ),
    ACCOUNTS_MANAGER: (
        ("accounts", "view_user"),
        ("wholesale", "view_wholesaleaccount"),
        ("wholesale", "change_wholesaleaccount"),
        ("wholesale", "review_wholesale_account"),
        ("locations", "view_address"),
        ("locations", "add_address"),
        ("locations", "change_address"),
    ),
}
