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
    CATALOGUE_MANAGER: (),
    INVENTORY_MANAGER: (),
    PRESCRIPTION_REVIEWER: (),
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
