import type { Metadata } from "next";

import { TeamQueueView } from "./team-queue-view";

export const metadata: Metadata = { title: "صف کار تیم" };

export default function TeamQueuePage() {
  return <TeamQueueView />;
}
