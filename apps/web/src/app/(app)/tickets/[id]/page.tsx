import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { TicketDetail } from "./ticket-detail";

export default function TicketPage({ params }: PageProps<"/tickets/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <Loader params={params} />
    </Suspense>
  );
}

async function Loader({ params }: { params: PageProps<"/tickets/[id]">["params"] }) {
  const { id } = await params;
  return <TicketDetail id={id} />;
}
