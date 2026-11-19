import type { Metadata } from "next";
import { Suspense } from "react";

import { Unsubscribe } from "./unsubscribe";

export const metadata: Metadata = { title: "لغو دریافت پیام", robots: { index: false } };

export default function UnsubscribePage({ params }: PageProps<"/u/[token]">) {
  return (
    <main className="grid min-h-svh place-items-center bg-background p-4">
      <Suspense fallback={null}>
        <TokenLoader params={params} />
      </Suspense>
    </main>
  );
}

async function TokenLoader({ params }: { params: PageProps<"/u/[token]">["params"] }) {
  const { token } = await params;
  return <Unsubscribe token={token} />;
}
