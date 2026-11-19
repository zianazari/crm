import type { ReactNode } from "react";
import { Lock } from "lucide-react";

import { UserAvatar } from "@/components/crm/user-avatar";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { LEAD_STATUS_LABELS, type LeadStatus, type UserRef } from "@/lib/types";

const STATUS_STYLES: Record<LeadStatus, string> = {
  new: "bg-secondary text-secondary-foreground",
  working: "bg-sky-50 text-sky-800",
  qualified: "bg-success text-success-foreground",
  disqualified: "bg-destructive/10 text-destructive",
  converted: "bg-violet-50 text-violet-800",
};

export function LeadStatusBadge({ status }: { status: LeadStatus }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", STATUS_STYLES[status])}>
      {LEAD_STATUS_LABELS[status]}
    </Badge>
  );
}

export function Owner({ user, className }: { user: UserRef; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <UserAvatar user={user} />
      <span className="truncate">{user.full_name}</span>
    </span>
  );
}

/** Marks a record the user can only see the current status of (spec section 0, decision 4). */
export function LimitedMark() {
  return (
    <Lock
      className="inline size-3.5 text-muted-foreground"
      aria-label="فقط وضعیت فعلی قابل مشاهده است"
    />
  );
}

export function Field({
  label,
  htmlFor,
  required,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {required ? <span className="text-destructive" aria-hidden> *</span> : null}
      </Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function InfoRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-3 text-sm last:border-b-0">
      <span className="flex items-center gap-2 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="min-w-0 text-end font-medium">{children}</span>
    </div>
  );
}
