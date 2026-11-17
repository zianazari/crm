import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { CustomerDetail } from "./customer-detail";

export default function CustomerPage({ params }: PageProps<"/customers/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <CustomerDetailLoader params={params} />
    </Suspense>
  );
}

async function CustomerDetailLoader({ params }: { params: PageProps<"/customers/[id]">["params"] }) {
  const { id } = await params;
  return <CustomerDetail id={id} />;
}
