import { Suspense } from "react";

import { DetailSkeleton } from "@/components/crm/detail-parts";
import { RuleEditor } from "./rule-editor";

export default function AutomationPage({ params }: PageProps<"/automations/[id]">) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <RuleEditorLoader params={params} />
    </Suspense>
  );
}

async function RuleEditorLoader({ params }: { params: PageProps<"/automations/[id]">["params"] }) {
  const { id } = await params;
  return <RuleEditor id={id} />;
}
