from __future__ import annotations

try:
    from vercel.headers import set_headers
except ImportError:
    set_headers = None


class VercelOidcHeaderMiddleware:
    # Register Vercel request headers with the Python SDK so Blob can
    # read the short-lived x-vercel-oidc-token runtime credential.

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if set_headers is not None:
            try:
                set_headers(request.headers)
            except Exception:
                # Local/non-Vercel requests do not need OIDC registration.
                pass

        return self.get_response(request)
