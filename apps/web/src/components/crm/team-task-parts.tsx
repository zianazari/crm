"use client";

import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { formatDate, formatMobile, formatToman } from "@/lib/format";
import type { ActivityType, Priority, Ref, UserRef } from "@/lib/types";
import { DEAL_STATUS_LABELS, type DealStatus } from "@/lib/types";

export type TaskContext = {
  contact_name: string | null;
  mobile: string | null;
  phone: string | null;
  email: string | null;
  deal_title: string | null;
  deal_status: DealStatus | null;
  stage: string | null;
  amount: number | null;
  contract_amount: number | null;
  contract_date: string | null;
  paid: number;
  balance: number | null;
};

export type TeamTask = {
  id: string;
  team: Ref;
  type: ActivityType;
  title: string;
  description: string | null;
  due_date: string;
  priority: Priority;
  status: "open" | "assigned" | "canceled";
  created_at: string;
  created_by: UserRef;
  assigned_to: UserRef | null;
  assigned_at: string | null;
  cancel_reason: string | null;
  lead: Ref | null;
  customer: Ref | null;
  deal: Ref | null;
  activity_id: string | null;
  context: TaskContext | null;
  can_manage: boolean;
  can_claim: boolean;
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-end font-medium">{children}</dd>
    </div>
  );
}

/** The deal details a finance task needs (spec section 5) — and only those. */
export function TaskContextView({ context }: { context: TaskContext }) {
  return (
    <dl className="divide-y text-sm">
      {context.contact_name ? <Row label="مخاطب">{context.contact_name}</Row> : null}
      {context.mobile ? (
        <Row label="موبایل">
          <a href={`tel:${context.mobile}`} className="ltr-value text-primary hover:underline">
            {formatMobile(context.mobile)}
          </a>
        </Row>
      ) : null}
      {context.phone ? <Row label="تلفن"><span className="ltr-value">{context.phone}</span></Row> : null}
      {context.email ? <Row label="ایمیل"><span className="ltr-value break-all">{context.email}</span></Row> : null}
      {context.deal_title ? (
        <Row label="فروش">
          {context.deal_title}
          {context.deal_status && context.deal_status !== "open" ? ` (${DEAL_STATUS_LABELS[context.deal_status]})` : context.stage ? ` (${context.stage})` : ""}
        </Row>
      ) : null}
      {context.contract_amount !== null ? (
        <Row label="مبلغ قرارداد">
          {formatToman(context.contract_amount)}
          {context.contract_date ? <span className="ms-1 text-xs text-muted-foreground">— {formatDate(context.contract_date)}</span> : null}
        </Row>
      ) : context.amount !== null ? (
        <Row label="مبلغ تخمینی">{formatToman(context.amount)}</Row>
      ) : null}
      {context.deal_title ? <Row label="دریافت‌شده">{formatToman(context.paid)}</Row> : null}
      {context.balance !== null ? (
        <Row label="مانده">
          <span className={context.balance > 0 ? "text-amber-800" : "text-emerald-700"}>{formatToman(context.balance)}</span>
        </Row>
      ) : null}
    </dl>
  );
}

/** On an activity that came from a team queue: its deal details, in a dialog. */
export function TaskContextButton({ taskId }: { taskId: string }) {
  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs">
            <Landmark aria-hidden />
            اطلاعات مالی
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>اطلاعات مالی</DialogTitle>
          <DialogDescription>جزئیات لازم برای این کار از صف تیم.</DialogDescription>
        </DialogHeader>
        <ContextLoader taskId={taskId} />
      </DialogContent>
    </Dialog>
  );
}

function ContextLoader({ taskId }: { taskId: string }) {
  const { data, error } = useQuery({
    queryKey: ["team-tasks", taskId],
    queryFn: () => apiFetch<TeamTask>(`/team-tasks/${taskId}`),
  });
  if (error) return <p className="text-sm text-destructive">{error.message}</p>;
  if (!data?.context) return <Skeleton className="h-40" />;
  return <TaskContextView context={data.context} />;
}
