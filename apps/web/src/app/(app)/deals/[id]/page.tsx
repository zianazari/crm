import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { DealDetail } from "./deal-detail";

export default function DealPage({ params }: PageProps<"/deals/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <DealDetailLoader params={params} />
    </Suspense>
  );
}

async function DealDetailLoader({ params }: { params: PageProps<"/deals/[id]">["params"] }) {
  const { id } = await params;
  return <DealDetail id={id} />;
}
