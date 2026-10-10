import ProductClient from "@/components/ProductClient";

export default async function ProductPage({ params, searchParams }: { params: Promise<{ sku: string }>; searchParams: Promise<{ prescription_id?: string; lens_id?: string }> }) {
  const { sku } = await params;
  const query = await searchParams;
  const prescriptionId = query.prescription_id ? Number(query.prescription_id) : undefined;
  const lensId = query.lens_id ? Number(query.lens_id) : undefined;
  return <ProductClient sku={decodeURIComponent(sku)} initialPrescriptionId={Number.isFinite(prescriptionId) ? prescriptionId : undefined} initialLensId={Number.isFinite(lensId) ? lensId : undefined}/>;
}
