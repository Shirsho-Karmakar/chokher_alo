import type { ProductDetail, ProductSummary } from "./api-types";

const demoNames = [
  "Aster Black",
  "Arc Steel",
  "Mauve Line",
  "Rosewood",
  "Edge Silver",
  "Blush Cat-Eye",
  "Graphite Square",
  "Ruby Line",
  "Wine Oval",
  "Midnight Red",
  "Minimal Rim",
  "Scarlet Edge",
  "Classic Black",
  "Ocean Blue",
  "Smoke Fade"
];

const prices = [1099, 1799, 1599, 1099, 1799, 1299, 1999, 1999, 1699, 1799, 1899, 1799, 2099, 1599, 2099];

export const demoProducts: ProductSummary[] = demoNames.map((name, index) => ({
  sku: `DEMO-${String(index + 1).padStart(3, "0")}`,
  name,
  supplier_model_number: `CA-${String(index + 1).padStart(3, "0")}`,
  brand: "Chokher Alo",
  offer_type: "frame_only",
  offer_type_label: "Frame only",
  colour: {
    id: index + 1,
    name: ["Black", "Steel", "Mauve", "Wine", "Silver", "Rose", "Graphite", "Red", "Wine", "Black", "Black", "Red", "Black", "Blue", "Smoke"][index],
    hex_value: null
  },
  size: "Medium",
  gender: index % 4 === 2 ? "women" : "unisex",
  gender_label: index % 4 === 2 ? "Women" : "Unisex",
  status: "available",
  status_label: "Available",
  price_visible: true,
  mrp_including_gst: String(Math.round(prices[index] / 0.7)),
  selling_price_including_gst: String(prices[index]),
  gst_rate: "18.00",
  requires_prescription: false,
  supports_powered_lenses: true,
  primary_image: {
    id: index + 1,
    url: `/products/frame-${String(index + 1).padStart(2, "0")}.jpg`,
    alt_text: `${name} optical frame`,
    is_primary: true,
    display_order: 0
  },
  detail_url: `/product/DEMO-${String(index + 1).padStart(3, "0")}`
}));

export function demoProductDetail(sku: string): ProductDetail | null {
  const summary = demoProducts.find((product) => product.sku === sku);
  if (!summary) return null;

  return {
    ...summary,
    description:
      "A lightweight everyday optical frame selected for comfort, clean proportions and easy prescription-lens pairing.",
    categories: [{ id: 1, name: "Eyeglasses", slug: "eyeglasses" }],
    attributes: {
      material: { id: 1, name: "Acetate blend" },
      frame_shape: { id: 1, name: "Contemporary" },
      frame_type: { id: 1, name: "Full rim" }
    },
    measurements_mm: {
      lens_width: "52",
      lens_height: "39",
      frame_width: "138"
    },
    physical_sku: summary.sku,
    supplier_variant_code: summary.supplier_model_number,
    images: summary.primary_image ? [summary.primary_image] : [],
    purchase_options: {
      direct_purchase_allowed: true,
      requires_prescription: false,
      supports_powered_lenses: true,
      compatible_lens_endpoint: "/lenses/compatible/"
    },
    other_offers_for_variant: []
  };
}

export const demoEnabled = process.env.NEXT_PUBLIC_DEMO_CATALOG !== "false";
