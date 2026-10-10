export type Money = string | null;

export type ProductImage = {
  id: number;
  url: string;
  alt_text: string;
  is_primary: boolean;
  display_order: number;
};

export type ProductSummary = {
  sku: string;
  name: string;
  supplier_model_number: string | null;
  brand: string | null;
  offer_type: string;
  offer_type_label: string;
  colour: { id: number; name: string; hex_value: string | null };
  size: string | null;
  gender: string;
  gender_label: string;
  status: string;
  status_label: string;
  price_visible: boolean;
  mrp_including_gst: Money;
  selling_price_including_gst: Money;
  gst_rate: Money;
  requires_prescription: boolean;
  supports_powered_lenses: boolean;
  primary_image: ProductImage | null;
  detail_url: string;
};

export type ProductDetail = ProductSummary & {
  description: string;
  categories: Array<{ id: number; name: string; slug: string }>;
  attributes: {
    material: { id: number; name: string } | null;
    frame_shape: { id: number; name: string } | null;
    frame_type: { id: number; name: string } | null;
  };
  measurements_mm: {
    lens_width: Money;
    lens_height: Money;
    frame_width: Money;
  };
  physical_sku: string;
  supplier_variant_code: string | null;
  images: ProductImage[];
  purchase_options: {
    direct_purchase_allowed: boolean;
    requires_prescription: boolean;
    supports_powered_lenses: boolean;
    compatible_lens_endpoint: string | null;
  };
  other_offers_for_variant: ProductSummary[];
};

export type Pagination = {
  page: number;
  page_size: number;
  total_pages: number;
  total_items: number;
  has_next: boolean;
  has_previous: boolean;
};

export type CatalogueFilters = {
  categories: Array<{ id: number; name: string; slug: string }>;
  brands: Array<{ id: number; name: string }>;
  colours: Array<{ id: number; name: string; hex_value: string }>;
  materials: Array<{ id: number; name: string }>;
  frame_shapes: Array<{ id: number; name: string }>;
  frame_types: Array<{ id: number; name: string }>;
  genders: Array<{ value: string; label: string }>;
  offer_types: Array<{ value: string; label: string }>;
};

export type Prescription = {
  id: number;
  status: string;
  status_label: string;
  customer_notes: string;
  customer_review_message: string | null;
  is_approved: boolean;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  file_download_url: string;
  eye_values: Array<{
    eye: string;
    eye_label: string;
    sphere: string | null;
    cylinder: string | null;
    axis: number | null;
    add_power: string | null;
    distance_pd_mm: string | null;
    near_pd_mm: string | null;
    prism_diopters: string | null;
    prism_base: string | null;
    prism_base_label: string | null;
  }>;
};

export type Lens = {
  lens_id: number;
  offer_id: number;
  sku: string;
  physical_sku: string;
  name: string;
  supplier_model_number: string | null;
  brand: string | null;
  vision_type: { id: number; code: string; name: string };
  refractive_index: { id: number; value: string; display_name: string | null };
  coatings: Array<{ id: number; code: string; name: string }>;
  selling_unit: string;
  selling_unit_label: string;
  units_per_box: number;
  requires_both_eyes: boolean;
  status: string;
  status_label: string;
  price_visible: boolean;
  mrp_including_gst: Money;
  base_price_including_gst: Money;
  gst_rate: Money;
};

export type CartItem = {
  id: number;
  item_type: string;
  item_type_label: string;
  offer: null | {
    sku: string;
    name: string;
    offer_type: string;
    offer_type_label: string;
    colour: string;
    size: string | null;
    status: string;
    supports_powered_lenses: boolean;
  };
  quantity: number;
  quantity_editable: boolean;
  current_unit_price_including_gst: Money;
  current_total_including_gst: Money;
  price_refreshed_at: string | null;
  is_non_refundable: boolean;
  powered_configuration: null | {
    state: string;
    prescription: { id: number; status: string; status_label: string; is_approved: boolean };
    lens: null | {
      id: number;
      sku: string;
      name: string;
      vision_type: { code: string; name: string };
      refractive_index: string;
      selling_unit: string;
      selling_unit_label: string;
    };
    selected_coatings: Array<{ id: number; code: string; name: string }>;
    lens_quote_breakdown: unknown;
    lens_quote_total_including_gst: Money;
    configured_unit_price_including_gst: Money;
    quote_refreshed_at: string | null;
  };
  customer_owned_frame_service: unknown;
};

export type Cart = {
  id: number;
  status: string;
  status_label: string;
  currency: string;
  last_validated_at: string | null;
  items: CartItem[];
  totals: { subtotal_including_gst: Money };
  validation: {
    checkout_ready: boolean;
    has_unpriced_items: boolean;
    issues: Array<{ code: string; message: string; item_id: number | null; blocking: boolean }>;
    removed_item_ids: number[];
  };
};

export type RetailOrderSummary = {
  order_number: string;
  status: string;
  status_label: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  payment_status_label: string;
  fulfillment_method: string;
  fulfillment_method_label: string;
  subtotal_including_gst: Money;
  delivery_fee_including_gst: Money;
  grand_total_including_gst: Money;
  currency: string;
  created_at: string;
  updated_at: string;
  can_customer_cancel?: boolean;
  cancellation_block_reason?: string | null;
};

export type ApiErrorPayload = {
  ok: false;
  error: {
    code: string;
    message: string;
    fields?: Record<string, unknown>;
    [key: string]: unknown;
  };
};

export type SessionStatus = {
  ok: true;
  authenticated: boolean;
  account_mode: "retail" | "wholesale" | null;
  user: null | {
    id: number;
    phone_number: string | null;
    phone_verified: boolean;
    email: string | null;
    first_name: string;
    last_name: string;
  };
  wholesale: null | {
    reference_id: string;
    status: string;
    status_label: string;
    is_approved: boolean;
  };
};

export type Address = {
  id: number;
  label: string;
  recipient_name: string;
  phone_number: string;
  address_line_1: string;
  address_line_2: string;
  landmark: string;
  city: string;
  district: string;
  state: string;
  state_label: string;
  postal_code: string;
  is_default_delivery: boolean;
  is_default_billing: boolean;
  is_active: boolean;
  updated_at: string;
};

export type Serviceability = {
  ok: true;
  postal_code: string;
  serviceable: boolean;
  status: string;
  status_label: string;
  city?: string | null;
  district?: string | null;
  state?: string;
  state_label?: string;
  message: string;
};

export type RetailOrderDetail = RetailOrderSummary & {
  can_customer_cancel: boolean;
  cancellation_block_reason: string | null;
  customer_notes: string | null;
  addresses: Array<Record<string, any>>;
  items: Array<{
    id: number;
    item_type: string;
    item_type_label: string;
    sku: string;
    product_name: string;
    variant_description: string | null;
    quantity: number;
    unit_price_including_gst: Money;
    line_total_including_gst: Money;
    is_custom: boolean;
    is_non_refundable: boolean;
    product_snapshot: Record<string, unknown>;
    configuration_snapshot: Record<string, unknown>;
  }>;
  fulfillment_groups: Array<{
    id: number;
    group_type: string;
    group_type_label: string;
    title: string;
    status: string;
    status_label: string;
    carrier_name: string | null;
    tracking_number: string | null;
  }>;
};

export type CheckoutPreview = {
  cart_id: number;
  fulfillment_method: string;
  payment_method: string;
  shipping_address: Record<string, unknown> | null;
  billing_address: Record<string, unknown>;
  billing_same_as_shipping: boolean;
  store_location: Record<string, unknown> | null;
  subtotal_including_gst: Money;
  delivery_fee_including_gst: Money;
  grand_total_including_gst: Money;
  currency: string;
  policy: {
    policy_id: number;
    name: string;
    delivery_fee_including_gst: string;
    free_delivery_threshold_including_gst: string;
    payment_reservation_minutes: number;
    cancellation_window_hours: number;
    pay_at_store_enabled: boolean;
    cod_enabled: boolean;
    currency: string;
  };
};

export type PaymentSession = {
  provider: "razorpay";
  key_id: string;
  provider_order_id: string;
  amount_subunits: number;
  currency: string;
  receipt: string;
  allowed_payment_methods: string[];
  expires_at: string | null;
};

export type WholesaleProfile = {
  reference_id: string;
  status: string;
  status_label: string;
  business_name: string;
  contact_person_name: string;
  gstin: string;
  invoice_email: string;
  missing_checkout_details: string[];
  business_details_complete: boolean;
  is_checkout_ready: boolean;
};

export type WholesaleVariant = {
  variant_id: number;
  sku: string;
  catalogue_code: string;
  name: string;
  product_name: string;
  brand: string | null;
  vision_type: { id: number; code: string; name: string };
  refractive_index: { id: number; value: string; display_name: string | null };
  coating: { id: number; code: string; name: string } | null;
  power: { label: string; sphere: string | null; cylinder: string | null; add_power: string | null; rule_name: string };
  box: { contents_unit: string; contents_unit_label: string; units_per_box: number };
  boxes_in_stock: number;
  minimum_order_boxes: number;
  order_multiple_boxes: number;
  status: string;
  status_label: string;
  price_visible: boolean;
  base_box_price_including_gst: Money;
  bulk_price_tiers: Array<{ id: number; minimum_boxes: number; maximum_boxes: number | null; box_price_including_gst: Money }>;
  public_notes: string;
};

export type WholesaleCart = {
  id: number;
  status: string;
  status_label: string;
  items: Array<{
    id: number;
    variant_id: number;
    sku: string;
    name: string;
    prescription_id: number | null;
    eye: string;
    eye_label: string;
    power_label: string;
    units_per_box: number;
    boxes: number;
    minimum_order_boxes: number;
    order_multiple_boxes: number;
    applied_box_price_including_gst: Money;
    subtotal_including_gst: Money;
    validation_status: string;
    validation_message: string | null;
  }>;
  readiness: {
    ready: boolean;
    subtotal_including_gst: Money;
    total_boxes: number;
    missing_checkout_details: string[];
    errors: string[];
    invalid_item_ids: number[];
  };
};

export type WholesaleOrderSummary = {
  order_number: string;
  status: string;
  status_label: string;
  payment_status: string;
  payment_status_label: string;
  fulfillment_status: string;
  fulfillment_status_label: string;
  total_boxes: number;
  subtotal_including_gst: Money;
  delivery_fee_including_gst: Money;
  grand_total_including_gst: Money;
  created_at: string;
  updated_at: string;
};

export type WholesaleOrderDetail = WholesaleOrderSummary & {
  business: Record<string, unknown>;
  customer_notes: string;
  placed_at: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  billing_address: {
    recipient_name: string;
    business_name: string;
    phone_number: string;
    invoice_email: string;
    gstin: string | null;
    address_line_1: string;
    address_line_2: string | null;
    landmark: string | null;
    city: string;
    district: string | null;
    state: string;
    postal_code: string;
  };
  fulfillment: {
    status: string;
    status_label: string;
    carrier_name: string | null;
    tracking_number: string | null;
    processing_started_at: string | null;
    shipped_at: string | null;
    delivered_at: string | null;
  };
  items: Array<{
    id: number;
    sku: string | null;
    catalogue_code: string | null;
    name: string | null;
    eye: string;
    boxes: number;
    physical_units: number;
    box_price_including_gst: Money;
    subtotal_including_gst: Money;
    variant_snapshot: Record<string, unknown>;
    prescription_snapshot: Record<string, unknown>;
    pricing_snapshot: Record<string, unknown>;
  }>;
  payment_attempts: Array<{
    id: number;
    method: string;
    method_label: string;
    status: string;
    status_label: string;
    amount_including_gst: Money;
    currency: string;
    provider_order_id: string | null;
    provider_payment_id: string | null;
    signature_verified: boolean;
    expires_at: string | null;
    paid_at: string | null;
  }>;
};

export type ProductStockAlert = {
  id: number;
  sku: string;
  channel: "sms" | "email";
  channel_label: string;
  destination: string;
  status: string;
  created_at: string;
};
