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


# Permissions for future applications will be added as those applications
# are implemented.
STAFF_GROUP_PERMISSIONS = {
    CATALOGUE_MANAGER: (),
    INVENTORY_MANAGER: (),
    PRESCRIPTION_REVIEWER: (),
    ORDER_MANAGER: (),
    ACCOUNTS_MANAGER: (
        ("accounts", "view_user"),
        ("wholesale", "view_wholesaleaccount"),
        ("wholesale", "change_wholesaleaccount"),
        ("wholesale", "review_wholesale_account"),
    ),
}
