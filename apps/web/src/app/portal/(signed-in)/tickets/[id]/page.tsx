import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { PortalTicketView } from "./portal-ticket";

export default function PortalTicketPage({ params }: PageProps<"/portal/tickets/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Loader params={params} />
    </Suspense>
  );
}

async function Loader({ params }: { params: PageProps<"/portal/tickets/[id]">["params"] }) {
  const { id } = await params;
  return <PortalTicketView id={id} />;
}
