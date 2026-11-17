import { CircleCheck, CircleX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Deal } from "@/lib/types";

/** Stage for open deals; result for closed ones, always with text and an icon. */
export function DealStatusBadge({ deal }: { deal: Pick<Deal, "status" | "stage"> }) {
  if (deal.status === "won") {
    return (
      <Badge variant="secondary" className="bg-success text-success-foreground">
        <CircleCheck aria-hidden />
        فروش انجام شد
      </Badge>
    );
  }
  if (deal.status === "lost") {
    return (
      <Badge variant="secondary" className="bg-destructive/10 text-destructive">
        <CircleX aria-hidden />
        به نتیجه نرسید
      </Badge>
    );
  }
  return <Badge variant="outline">{deal.stage.name}</Badge>;
}
