import { Badge } from "@/components/ui/badge";
import type { TicketStatus } from "@/lib/portal";
import { cn } from "@/lib/utils";

export const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  new: "جدید",
  in_progress: "در حال بررسی",
  waiting_customer: "منتظر پاسخ مشتری",
  closed: "بسته‌شده",
};

const STYLES: Record<TicketStatus, string> = {
  new: "bg-sky-50 text-sky-800",
  in_progress: "bg-amber-100 text-amber-900",
  waiting_customer: "bg-violet-50 text-violet-800",
  closed: "bg-muted text-muted-foreground",
};

/** ``label`` lets the portal say «منتظر پاسخ شما» where staff read «منتظر پاسخ مشتری». */
export function TicketStatusBadge({ status, label }: { status: TicketStatus; label?: string }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", STYLES[status])}>
      {label ?? TICKET_STATUS_LABELS[status]}
    </Badge>
  );
}
