from django.http import JsonResponse


class AccountModeIsolationMiddleware:
    """Strictly isolate retail and wholesale authenticated sessions."""

    WHOLESALE_PREFIXES = (
        "/wholesale/",
        "/api/wholesale/",
    )

    RETAIL_PREFIXES = (
        "/catalogue/",
        "/prescriptions/",
        "/lenses/",
        "/cart/",
        "/retail/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _blocked(message):
        return JsonResponse(
            {
                "ok": False,
                "error": {
                    "code": "account_mode_mismatch",
                    "message": message,
                },
            },
            status=403,
        )

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            not user
            or not getattr(user, "is_authenticated", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        ):
            return self.get_response(request)

        path = request.path
        mode = request.session.get("account_mode", "retail")

        if mode == "wholesale":
            if path.startswith(self.RETAIL_PREFIXES):
                return self._blocked(
                    "This wholesale session cannot access the retail store. "
                    "Sign out, then sign in through Retail."
                )

        elif mode == "retail":
            if path.startswith(self.WHOLESALE_PREFIXES):
                return self._blocked(
                    "This retail session cannot access the wholesale store. "
                    "Sign out, then sign in through Wholesale."
                )

        else:
            request.session["account_mode"] = "retail"
            request.session.modified = True

        return self.get_response(request)
