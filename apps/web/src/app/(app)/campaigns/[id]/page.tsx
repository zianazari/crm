import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { CampaignDetail } from "./campaign-detail";

export default function CampaignPage({ params }: PageProps<"/campaigns/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <CampaignLoader params={params} />
    </Suspense>
  );
}

async function CampaignLoader({ params }: { params: PageProps<"/campaigns/[id]">["params"] }) {
  const { id } = await params;
  return <CampaignDetail id={id} />;
}
