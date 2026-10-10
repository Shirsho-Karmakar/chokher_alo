import type {
  ApiErrorPayload,
  Cart,
  CatalogueFilters,
  Lens,
  Pagination,
  Prescription,
  ProductDetail,
  ProductSummary,
  RetailOrderSummary
} from "./api-types";

const API_PREFIX = process.env.NEXT_PUBLIC_API_PREFIX || "/backend";
let csrfPromise: Promise<void> | null = null;

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(message: string, code = "api_error", status = 500, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function cookie(name: string) {
  if (typeof document === "undefined") return null;
  const found = document.cookie
    .split(";")
    .map((v) => v.trim())
    .find((v) => v.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.split("=").slice(1).join("=")) : null;
}

async function ensureCsrf() {
  if (typeof window === "undefined" || cookie("csrftoken")) return;
  if (!csrfPromise) {
    csrfPromise = fetch(`${API_PREFIX}/auth/csrf/`, {
      method: "GET",
      credentials: "include",
      cache: "no-store"
    }).then(() => undefined).finally(() => {
      csrfPromise = null;
    });
  }
  await csrfPromise;
}

async function refreshCsrf() {
  if (typeof window === "undefined") return;

  document.cookie = "csrftoken=; Max-Age=0; path=/; SameSite=Lax";

  await fetch(`${API_PREFIX}/auth/csrf/`, {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });
}

async function request<T>(path: string, init: RequestInit = {}, retryCsrf = true): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    await ensureCsrf();
    const token = cookie("csrftoken");
    if (token) headers.set("X-CSRFToken", token);
  }

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store"
  });

  // Django rotates the CSRF token when a user logs in.
  // If the browser still has the previous token, refresh it once
  // and repeat the POST automatically.
  if (
    response.status === 403 &&
    retryCsrf &&
    !["GET", "HEAD", "OPTIONS"].includes(method)
  ) {
    await refreshCsrf();
    return request<T>(path, init, false);
  }

  const contentType = response.headers.get("content-type") || "";
  const redirectedToLogin = response.redirected && (
    response.url.includes("/accounts/login/") ||
    response.url.includes("/wholesale/login/")
  );
  if (!contentType.includes("application/json")) {
    if (redirectedToLogin || response.status === 401) {
      throw new ApiError("Sign in to continue.", "authentication_required", response.status || 401);
    }

    if (response.status === 403) {
      throw new ApiError(
        "The request was rejected by the server. Refresh the page and try again.",
        "request_forbidden",
        403
      );
    }
    if (!response.ok) {
      throw new ApiError("The server returned an unexpected response.", "non_json_response", response.status);
    }
    throw new ApiError("The server did not return JSON.", "non_json_response", response.status);
  }

  const payload = (await response.json()) as T | ApiErrorPayload;
  if (!response.ok || (typeof payload === "object" && payload && "ok" in payload && payload.ok === false)) {
    const errorPayload = payload as ApiErrorPayload;
    throw new ApiError(
      errorPayload.error?.message || "Something went wrong.",
      errorPayload.error?.code || "api_error",
      response.status,
      errorPayload.error
    );
  }
  return payload as T;
}

export function postForm<T>(path: string, values: Record<string, string | number | boolean | Array<string | number> | null | undefined>) {
  const form = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((item) => form.append(key, String(item)));
    } else {
      form.append(key, typeof value === "boolean" ? (value ? "on" : "") : String(value));
    }
  }
  return request<T>(path, {
    method: "POST",
    body: form,
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" }
  });
}

export function postMultipart<T>(path: string, form: FormData) {
  return request<T>(path, { method: "POST", body: form });
}

export async function getCatalogueFilters() {
  const data = await request<{ ok: true; filters: CatalogueFilters }>("/catalogue/filters/");
  return data.filters;
}

export async function getProducts(params: URLSearchParams | Record<string, string | number | undefined> = {}) {
  const query = params instanceof URLSearchParams ? new URLSearchParams(params) : new URLSearchParams();
  if (!(params instanceof URLSearchParams)) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{ ok: true; pagination: Pagination; products: ProductSummary[] }>(`/catalogue/products/${suffix}`);
}

export async function getProduct(sku: string) {
  const data = await request<{ ok: true; product: ProductDetail }>(`/catalogue/products/${encodeURIComponent(sku)}/`);
  return data.product;
}

export async function requestRetailOtp(phoneNumber: string) {
  return postForm<{ ok: true; challenge_id: string; expires_in_seconds: number; resend_after_seconds: number; development_otp?: string }>(
    "/auth/phone/request/",
    { phone_number: phoneNumber }
  );
}

export async function verifyRetailOtp(challengeId: string, code: string) {
  return postForm<{ ok: true; user_created: boolean; phone_number: string; redirect_url: string }>(
    "/auth/phone/verify/",
    { challenge_id: challengeId, code }
  );
}

export async function requestWholesaleOtp(phoneNumber: string) {
  return postForm<{ ok: true; challenge_id: string; expires_in_seconds: number; resend_after_seconds: number; development_otp?: string }>(
    "/wholesale/auth/phone/request/",
    { phone_number: phoneNumber }
  );
}

export async function verifyWholesaleOtp(challengeId: string, code: string) {
  return postForm<{
    ok: true;
    user_created: boolean;
    phone_number: string;
    redirect_url: string;
    wholesale: { created: boolean; reference_id: string; status: string };
  }>("/wholesale/auth/phone/verify/", { challenge_id: challengeId, code });
}

export function prescriptionFileUrl(fileDownloadUrl: string, inline = false) {
  const path = fileDownloadUrl.startsWith("/") ? fileDownloadUrl : `/${fileDownloadUrl}`;
  const separator = path.includes("?") ? "&" : "?";
  return `${API_PREFIX}${path}${inline ? `${separator}inline=1` : ""}`;
}

export async function getPrescriptions() {
  const data = await request<{ ok: true; prescriptions: Prescription[] }>("/prescriptions/");
  return data.prescriptions;
}

export async function uploadPrescription(form: FormData) {
  const data = await postMultipart<{ ok: true; prescription: Prescription }>("/prescriptions/upload/", form);
  return data.prescription;
}

export async function removePrescription(prescriptionId: number) {
  return postForm<{ ok: true; prescription_id: number; removed_from_account: true }>(
    `/prescriptions/${prescriptionId}/remove/`,
    {}
  );
}

export async function getCompatibleLenses(prescriptionId: number) {
  const data = await request<{ ok: true; count: number; lenses: Lens[] }>(
    `/lenses/compatible/?prescription_id=${prescriptionId}`
  );
  return data.lenses;
}

export async function addStandardItem(sku: string, quantity = 1) {
  return postForm<{ ok: true; cart: Cart }>("/cart/items/standard/", { sku, quantity });
}

export async function addPoweredItem(sku: string, prescriptionId: number) {
  return postForm<{ ok: true; cart: Cart; mutation: { item_id: number } }>("/cart/items/powered/", {
    sku,
    prescription_id: prescriptionId
  });
}

export async function configurePoweredItem(itemId: number, lensId: number, coatingIds: number[]) {
  return postForm<{ ok: true; cart: Cart }>(`/cart/items/powered/${itemId}/configure/`, {
    lens_id: lensId,
    coating_ids: coatingIds
  });
}

export async function getCart() {
  const data = await request<{ ok: true; cart: Cart }>("/cart/");
  return data.cart;
}

export async function updateCartQuantity(itemId: number, quantity: number) {
  const data = await postForm<{ ok: true; cart: Cart }>(`/cart/items/${itemId}/quantity/`, { quantity });
  return data.cart;
}

export async function removeCartItem(itemId: number) {
  const data = await postForm<{ ok: true; cart: Cart }>(`/cart/items/${itemId}/remove/`, {});
  return data.cart;
}

export async function getRetailOrders() {
  const data = await request<{ ok: true; pagination: Pagination; orders: RetailOrderSummary[] }>("/retail/orders/");
  return data.orders;
}

export async function getWholesaleStatus() {
  return request<{
    ok: true;
    reference_id: string;
    status: string;
    status_label: string;
    business_name: string;
    verification: { instructions: string; contacts: Array<{ label: string; phone_number: string }> };
  }>("/wholesale/status/");
}

export async function getWholesaleDashboard() {
  return request<{ ok: true; message: string; reference_id: string }>("/wholesale/dashboard/");
}

export async function getSession() {
  return request<import("./api-types").SessionStatus>("/auth/session/");
}

export async function logoutSession() {
  return postForm<{ ok: true }>("/auth/logout/", {});
}

export async function checkServiceability(postalCode: string) {
  return request<import("./api-types").Serviceability>(`/locations/serviceability/?postal_code=${encodeURIComponent(postalCode)}`);
}

export async function getAddresses() {
  const data = await request<{ ok: true; addresses: import("./api-types").Address[] }>("/locations/addresses/");
  return data.addresses;
}

export async function createAddress(values: Record<string, string | boolean>) {
  const data = await postForm<{ ok: true; address: import("./api-types").Address }>("/locations/addresses/", values);
  return data.address;
}

export async function updateAddress(id: number, values: Record<string, string | boolean>) {
  const data = await postForm<{ ok: true; address: import("./api-types").Address }>(`/locations/addresses/${id}/`, values);
  return data.address;
}

export async function removeAddress(id: number) {
  return postForm<{ ok: true }>(`/locations/addresses/${id}/deactivate/`, {});
}

export async function previewCheckout(values: Record<string, string | number | boolean>) {
  const data = await postForm<{ ok: true; preview: import("./api-types").CheckoutPreview }>("/retail/checkout/preview/", values);
  return data.preview;
}

export async function createCheckout(values: Record<string, string | number | boolean>) {
  return postForm<{ ok: true; order: import("./api-types").RetailOrderDetail; payment_session: import("./api-types").PaymentSession | null }>("/retail/checkout/create/", values);
}

export async function confirmRetailRazorpay(values: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) {
  return postForm<{ ok: true; order: import("./api-types").RetailOrderDetail }>("/retail/payments/razorpay/confirm/", values);
}

export async function getRetailOrder(orderNumber: string) {
  const data = await request<{ ok: true; order: import("./api-types").RetailOrderDetail }>(`/retail/orders/${encodeURIComponent(orderNumber)}/`);
  return data.order;
}

export async function cancelRetailOrder(orderNumber: string, reason: string) {
  const data = await postForm<{ ok: true; order: import("./api-types").RetailOrderDetail }>(`/retail/orders/${encodeURIComponent(orderNumber)}/cancel/`, { reason });
  return data.order;
}

export async function getWholesaleProfile() {
  const data = await request<{ ok: true; profile: import("./api-types").WholesaleProfile }>("/wholesale/profile/");
  return data.profile;
}

export async function updateWholesaleProfile(values: Record<string, string>) {
  const data = await postForm<{ ok: true; profile: import("./api-types").WholesaleProfile }>("/wholesale/profile/", values);
  return data.profile;
}

export async function getWholesaleCatalogue() {
  return request<{ ok: true; count: number; variants: import("./api-types").WholesaleVariant[]; wholesale_account: { checkout_ready: boolean; missing_checkout_details: string[] } }>("/wholesale/catalogue/lenses/");
}

export async function getWholesaleCart() {
  const data = await request<{ ok: true; cart: import("./api-types").WholesaleCart }>("/wholesale/cart/");
  return data.cart;
}

export async function setWholesaleCartItem(values: { variant_id: number; boxes: number }) {
  const data = await postForm<{ ok: true; cart: import("./api-types").WholesaleCart }>("/wholesale/cart/items/set/", values);
  return data.cart;
}

export async function removeWholesaleCartItem(itemId: number) {
  const data = await postForm<{ ok: true; cart: import("./api-types").WholesaleCart }>(`/wholesale/cart/items/${itemId}/remove/`, {});
  return data.cart;
}

export async function createWholesaleCheckout(paymentMethod: string, customerNotes = "") {
  return postForm<{ ok: true; order: import("./api-types").WholesaleOrderDetail; payment_session: import("./api-types").PaymentSession | null }>("/api/wholesale/checkout/create/", { payment_method: paymentMethod, customer_notes: customerNotes });
}

export async function confirmWholesaleRazorpay(values: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) {
  return postForm<{ ok: true; order: import("./api-types").WholesaleOrderDetail }>("/api/wholesale/payments/razorpay/confirm/", values);
}

export async function getWholesaleOrders() {
  const data = await request<{ ok: true; orders: import("./api-types").WholesaleOrderSummary[] }>("/api/wholesale/orders/");
  return data.orders;
}

export async function getWholesaleOrder(orderNumber: string) {
  const data = await request<{ ok: true; order: import("./api-types").WholesaleOrderDetail }>(`/api/wholesale/orders/${encodeURIComponent(orderNumber)}/`);
  return data.order;
}

export async function cancelWholesaleOrder(orderNumber: string, reason: string) {
  const data = await postForm<{ ok: true; order: import("./api-types").WholesaleOrderDetail }>(`/api/wholesale/orders/${encodeURIComponent(orderNumber)}/cancel/`, { reason });
  return data.order;
}

export async function getStockAlerts() {
  const data = await request<{ ok: true; alerts: import("./api-types").ProductStockAlert[] }>("/catalogue/stock-alerts/");
  return data.alerts;
}

export async function createStockAlert(sku: string, channel: "sms" | "email" = "sms") {
  return postForm<{ ok: true; created: boolean; alert: import("./api-types").ProductStockAlert }>("/catalogue/stock-alerts/create/", { sku, channel });
}

export async function cancelStockAlert(alertId: number) {
  return postForm<{ ok: true; alert_id: number; status: string }>(`/catalogue/stock-alerts/${alertId}/cancel/`, {});
}

/**
 * Catalogue images are served by authenticated/public Django views rather than
 * Next.js static assets. Route those URLs back through the same-origin proxy so
 * production can keep Django on a private upstream address.
 */
export function publicCatalogueImageUrl(value: string | null | undefined) {
  if (!value) return "";
  const marker = "/catalogue/images/";
  const markerIndex = value.indexOf(marker);
  if (markerIndex >= 0) return `${API_PREFIX}${value.slice(markerIndex)}`;
  return value;
}
