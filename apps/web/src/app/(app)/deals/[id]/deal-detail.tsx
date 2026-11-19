"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Archive,
  Banknote,
  Building2,
  CalendarDays,
  CircleCheck,
  CircleX,
  Pencil,
  RotateCcw,
  Undo2,
  UserRound,
  Wallet,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AssignDialog } from "@/components/crm/assign-dialog";
import { InfoRow, Owner } from "@/components/crm/bits";
import { CloseDealDialog, type CloseMode } from "@/components/crm/close-deal-dialog";
import { DealFormDialog } from "@/components/crm/deal-form-dialog";
import { DealStatusBadge } from "@/components/crm/deal-status";
import { Breadcrumb, DetailError, DetailSkeleton, LimitedRecord } from "@/components/crm/detail-parts";
import { PaymentDialog } from "@/components/crm/payment-dialog";
import { PlannedActivities, Timeline } from "@/components/crm/record-activity";
import { ReasonDialog } from "@/components/crm/reason-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { useMoveDeal } from "@/lib/deal-actions";
import { formatDate, formatToman } from "@/lib/format";
import { formatIsoDate } from "@/lib/jalali";
import { canManage, keys, useDeal, useDealPayments, useMe, useStages } from "@/lib/queries";
import { DEAL_STATUS_LABELS, type DealFull, type Stage } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DealDetail({ id }: { id: string }) {
  const { data: deal, isPending, error } = useDeal(id);
  if (isPending) return <DetailSkeleton />;
  if (error) return <DetailError error={error} />;

  return (
    <div className="space-y-6">
      <Breadcrumb href="/deals" label="فروش‌ها" current={deal.title} />
      {deal.access === "full" ? (
        <FullDeal deal={deal} />
      ) : (
        <LimitedRecord
          title={`${deal.title} — ${deal.customer.full_name}`}
          owner={deal.owner}
          status={<DealStatusBadge deal={deal} />}
          lastActivity={deal.last_activity_at}
        />
      )}
    </div>
  );
}

function FullDeal({ deal }: { deal: DealFull }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const [closing, setClosing] = useState<CloseMode | null>(null);
  const manager = canManage(me?.role);
  const open = deal.status === "open";
  const archived = Boolean(deal.archived_at);

  async function post(path: string, body: unknown, message: string): Promise<boolean> {
    try {
      await apiFetch(`/deals/${deal.id}/${path}`, { method: "POST", body: JSON.stringify(body) });
      toast.success(message);
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
      return false;
    } finally {
      await queryClient.invalidateQueries({ queryKey: keys.deals });
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold">پرونده فروش</h1>
            <DealStatusBadge deal={deal} />
            {archived ? <Badge variant="outline">بایگانی‌شده</Badge> : null}
          </div>
          <p className="text-muted-foreground">
            {deal.title} —{" "}
            <Link href={`/customers/${deal.customer.id}`} className="hover:text-foreground hover:underline">
              {deal.customer.full_name}
            </Link>
          </p>
        </div>
        {!archived ? (
          <div className="flex flex-wrap gap-2">
            {open ? (
              <>
                <Button onClick={() => setClosing("won")}>
                  <CircleCheck aria-hidden />
                  فروش انجام شد
                </Button>
                <Button variant="outline" onClick={() => setClosing("lost")}>
                  <CircleX aria-hidden />
                  به نتیجه نرسید
                </Button>
                <DealFormDialog
                  deal={deal}
                  trigger={
                    <Button variant="outline">
                      <Pencil aria-hidden />
                      ویرایش
                    </Button>
                  }
                />
              </>
            ) : manager ? (
              <ReasonDialog
                title="بازگشایی فروش"
                description="فروش دوباره باز می‌شود و اطلاعات قرارداد یا دلیل باخت در تاریخچه می‌ماند. گزارش‌ها این تغییر را نشان می‌دهند."
                confirmLabel="بازگشایی"
                trigger={
                  <Button variant="outline">
                    <RotateCcw aria-hidden />
                    بازگشایی
                  </Button>
                }
                onConfirm={(reason) => post("reopen", { reason, version: deal.version }, "فروش بازگشایی شد.")}
              />
            ) : null}
            {manager ? (
              <>
                <AssignDialog
                  path={`/deals/${deal.id}`}
                  currentOwner={deal.owner}
                  invalidate={keys.deals}
                  trigger={<Button variant="outline">تغییر مسئول</Button>}
                />
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (window.confirm("این فروش بایگانی شود؟ این کار با بستن فروش فرق دارد و در گزارش‌ها حساب نمی‌شود.")) {
                      void post("archive", {}, "فروش بایگانی شد.");
                    }
                  }}
                >
                  <Archive aria-hidden />
                  بایگانی
                </Button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>

      <StageStrip deal={deal} />

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          <PlannedActivities subject={{ deal: { id: deal.id, name: deal.title } }} filter={{ deal_id: deal.id }} />
          <Timeline subject={{ deal_id: deal.id }} />
          <MoneyCard deal={deal} manager={manager} />
        </div>

        <Card className="order-first h-fit lg:order-last">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserRound className="size-5" aria-hidden />
              خلاصه فروش
            </CardTitle>
          </CardHeader>
          <CardContent>
            <InfoRow icon={<UserRound className="size-4" />} label="مشتری">
              <Link href={`/customers/${deal.customer.id}`} className="text-primary hover:underline">
                {deal.customer.full_name}
              </Link>
            </InfoRow>
            <InfoRow icon={<Building2 className="size-4" />} label="سازمان">
              {deal.organization?.name ?? "خرید شخصی"}
            </InfoRow>
            <InfoRow icon={<UserRound className="size-4" />} label="مسئول فروش">
              <Owner user={deal.owner} />
            </InfoRow>
            <InfoRow icon={<CalendarDays className="size-4" />} label="بسته‌شدن احتمالی">
              {formatIsoDate(deal.expected_close_date)}
            </InfoRow>
            <InfoRow icon={<CalendarDays className="size-4" />} label="تاریخ ثبت">
              {formatDate(deal.created_at)}
            </InfoRow>
            {deal.status === "lost" ? (
              <InfoRow icon={<CircleX className="size-4" />} label="دلیل">
                {deal.lost_reason}
              </InfoRow>
            ) : null}
            {deal.description ? (
              <p className="whitespace-pre-line pt-3 text-sm leading-7 text-muted-foreground">{deal.description}</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {closing ? (
        <CloseDealDialog
          key={closing}
          deal={deal}
          mode={closing}
          onOpenChange={(isOpen) => !isOpen && setClosing(null)}
        />
      ) : null}
    </>
  );
}

/** Pipeline progress as in the design; clicking a stage moves an open deal there. */
function StageStrip({ deal }: { deal: DealFull }) {
  const { data: stages = [] } = useStages();
  const move = useMoveDeal();
  const currentIndex = stages.findIndex((s) => s.id === deal.stage.id);
  const movable = deal.status === "open" && !deal.archived_at;
  const amount = deal.status === "won" ? deal.contract_amount : deal.amount;

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <ol className="flex flex-wrap items-center gap-1" aria-label="مراحل فروش">
          {stages.map((stage: Stage, i) => {
            const done = deal.status !== "open" || i < currentIndex;
            const current = deal.status === "open" && i === currentIndex;
            return (
              <li key={stage.id}>
                <button
                  type="button"
                  disabled={!movable || current}
                  onClick={() => void move(deal, stage)}
                  aria-current={current ? "step" : undefined}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                    current && "border-primary bg-primary text-primary-foreground",
                    done && !current && "border-transparent bg-accent text-accent-foreground",
                    !done && !current && "text-muted-foreground",
                    movable && !current && "hover:border-primary",
                  )}
                >
                  {done && !current ? <CircleCheck className="size-4" aria-hidden /> : null}
                  {stage.name}
                </button>
              </li>
            );
          })}
          {deal.status !== "open" ? (
            <li>
              <span
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium",
                  deal.status === "won" ? "bg-primary text-primary-foreground" : "bg-destructive text-white dark:text-background",
                )}
              >
                {deal.status === "won" ? <CircleCheck className="size-4" aria-hidden /> : <CircleX className="size-4" aria-hidden />}
                {DEAL_STATUS_LABELS[deal.status]}
              </span>
            </li>
          ) : null}
        </ol>
        <div className="text-end">
          <p className="text-xs text-muted-foreground">{deal.status === "won" ? "مبلغ قرارداد" : "مبلغ تخمینی"}</p>
          <p className="text-xl font-bold text-primary">{amount !== null ? formatToman(amount) : "—"}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function MoneyCard({ deal, manager }: { deal: DealFull; manager: boolean }) {
  const queryClient = useQueryClient();
  const { data: payments = [] } = useDealPayments(deal.id, true);
  const canRecord = deal.status !== "lost" && !deal.archived_at;

  async function voidPayment(paymentId: string, reason: string) {
    try {
      await apiFetch(`/deals/${deal.id}/payments/${paymentId}/void`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      await queryClient.invalidateQueries({ queryKey: keys.deals });
      toast.success("پرداخت باطل شد.");
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
      return false;
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <Wallet className="size-5" aria-hidden />
          پرداخت‌ها
        </CardTitle>
        {canRecord ? (
          <div className="flex gap-2">
            <PaymentDialog
              dealId={deal.id}
              kind="payment"
              trigger={
                <Button size="sm">
                  <Banknote aria-hidden />
                  ثبت پرداخت
                </Button>
              }
            />
            {deal.paid_amount > 0 ? (
              <PaymentDialog
                dealId={deal.id}
                kind="refund"
                trigger={
                  <Button size="sm" variant="outline">
                    <Undo2 aria-hidden />
                    بازپرداخت
                  </Button>
                }
              />
            ) : null}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-3 sm:grid-cols-3">
          <Stat label="مبلغ قرارداد" value={deal.contract_amount !== null ? formatToman(deal.contract_amount) : "—"} />
          <Stat label="دریافت‌شده" value={formatToman(deal.paid_amount)} />
          <Stat
            label="مانده دریافت‌نشده"
            value={deal.outstanding_amount !== null ? formatToman(deal.outstanding_amount) : "—"}
            emphasis={deal.outstanding_amount !== null && deal.outstanding_amount > 0}
          />
        </dl>
        {deal.status === "open" ? (
          <p className="text-xs text-muted-foreground">
            مانده دریافت‌نشده پس از ثبت «فروش انجام شد» و مبلغ قرارداد محاسبه می‌شود.
          </p>
        ) : null}

        {payments.length ? (
          <ul className="divide-y rounded-lg border">
            {payments.map((p) => (
              <li key={p.id} className={cn("flex flex-wrap items-center justify-between gap-2 p-3 text-sm", p.voided_at && "opacity-60")}>
                <div className="space-y-0.5">
                  <p className={cn("font-medium", p.voided_at && "line-through")}>
                    {p.kind === "refund" ? "بازپرداخت " : ""}
                    {formatToman(p.amount)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatIsoDate(p.paid_on)} · ثبت: {p.recorded_by.full_name}
                    {p.reference ? (
                      <>
                        {" · مرجع: "}
                        <span className="ltr-value">{p.reference}</span>
                      </>
                    ) : null}
                  </p>
                  {p.voided_at ? <p className="text-xs text-destructive">باطل‌شده: {p.void_reason}</p> : null}
                </div>
                {manager && !p.voided_at ? (
                  <ReasonDialog
                    title="ابطال پرداخت"
                    description="پرداخت حذف نمی‌شود؛ با دلیل باطل و از جمع دریافتی کسر می‌شود."
                    confirmLabel="ابطال"
                    destructive
                    trigger={
                      <Button size="sm" variant="ghost">
                        ابطال
                      </Button>
                    }
                    onConfirm={(reason) => voidPayment(p.id, reason)}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">هنوز پرداختی ثبت نشده است.</p>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className={cn("rounded-lg border p-3", emphasis && "border-warning-foreground/30 bg-warning")}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 font-semibold", emphasis && "text-warning-foreground")}>{value}</dd>
    </div>
  );
}
