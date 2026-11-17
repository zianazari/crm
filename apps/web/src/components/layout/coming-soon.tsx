import { Construction } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

/** Placeholder for a release-1 page whose implementation has not started yet. */
export function ComingSoon({ summary }: { summary: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-accent text-accent-foreground">
          <Construction className="size-6" aria-hidden />
        </span>
        <p className="font-semibold">این بخش در حال ساخت است</p>
        <p className="max-w-md text-sm text-muted-foreground">{summary}</p>
      </CardContent>
    </Card>
  );
}
