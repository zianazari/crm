import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { LeadDetail } from "./lead-detail";

export default function LeadPage({ params }: PageProps<"/leads/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <LeadDetailLoader params={params} />
    </Suspense>
  );
}

async function LeadDetailLoader({ params }: { params: PageProps<"/leads/[id]">["params"] }) {
  const { id } = await params;
  return <LeadDetail id={id} />;
}
