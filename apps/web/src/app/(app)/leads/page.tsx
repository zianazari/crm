import type { Metadata } from "next";

import { LeadsView } from "./leads-view";

export const metadata: Metadata = { title: "مشتریان احتمالی" };

export default function LeadsPage() {
  return <LeadsView />;
}
