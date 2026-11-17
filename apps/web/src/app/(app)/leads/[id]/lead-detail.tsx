"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Archive,
  ArchiveRestore,
  AtSign,
  Building2,
  CalendarDays,
  Link2,
  Pencil,
  Phone,
  Tag,
  UserCheck,
  UserRound,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AssignDialog } from "@/components/crm/assign-dialog";
import { InfoRow, LeadStatusBadge, Owner } from "@/components/crm/bits";
import { ConvertDialog } from "@/components/crm/convert-dialog";
import { Breadcrumb, DetailError, DetailSkeleton, LimitedRecord } from "@/components/crm/detail-parts";
import { LeadFormDialog } from "@/components/crm/lead-form-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatDateTime, formatMobile } from "@/lib/format";
import { canManage, keys, useLead, useMe } from "@/lib/queries";
import { LEAD_STATUS_LABELS, type LeadFull, type LeadStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const EDITABLE_STATUSES: LeadStatus[] = ["new", "working", "qualified", "disqualified"];

export function LeadDetail({ id }: { id: string }) {
  const { data: lead, isPending, error } = useLead(id);
  if (isPending) return <DetailSkeleton />;
  if (error) return <DetailError error={error} />;

  return (
    <div className="space-y-6">
      <Breadcrumb href="/leads" label="مشتریان احتمالی" current={lead.full_name} />
      {lead.access === "full" ? (
        <FullLead lead={lead} />
      ) : (
        <LimitedRecord
          title={lead.full_name}
          owner={lead.owner}
          status={<LeadStatusBadge status={lead.status} />}
          lastActivity={lead.last_contacted_at}
        />
      )}
    </div>
  );
}

function FullLead({ lead }: { lead: LeadFull }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const converted = lead.status === "converted";
  const archived = Boolean(lead.archived_at);
  const editable = !converted && !archived;

  async function post(path: string, message: string) {
    try {
      await apiFetch(`/leads/${lead.id}/${path}`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: keys.leads });
      toast.success(message);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{lead.full_name}</h1>
            <LeadStatusBadge status={lead.status} />
            {archived ? <Badge variant="outline">بایگانی‌شده</Badge> : null}
          </div>
          {lead.company_name ? <p className="text-muted-foreground">{lead.company_name}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {editable ? (
            <>
              <ConvertDialog
                lead={lead}
                trigger={
                  <Button disabled={lead.status === "disqualified"}>
                    <UserCheck aria-hidden />
                    تبدیل به مشتری
                  </Button>
                }
              />
              <LeadFormDialog
                lead={lead}
                trigger={
                  <Button variant="outline">
                    <Pencil aria-hidden />
                    ویرایش
                  </Button>
                }
              />
            </>
          ) : null}
          {canManage(me?.role) && !converted ? (
            <>
              <AssignDialog
                path={`/leads/${lead.id}`}
                currentOwner={lead.owner}
                invalidate={keys.leads}
                trigger={<Button variant="outline">تغییر مسئول</Button>}
              />
              {archived ? (
                <Button variant="outline" onClick={() => void post("restore", "پرونده بازیابی شد.")}>
                  <ArchiveRestore aria-hidden />
                  بازیابی
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (window.confirm("این پرونده بایگانی شود؟ بعداً قابل بازیابی است.")) {
                      void post("archive", "پرونده بایگانی شد.");
                    }
                  }}
                >
                  <Archive aria-hidden />
                  بایگانی
                </Button>
              )}
            </>
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          {editable ? <StatusCard lead={lead} /> : null}
          {converted && lead.converted_customer_id ? (
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm">
                  این سرنخ در {formatDateTime(lead.converted_at)} به مشتری تبدیل شده است.
                </p>
                <Button variant="outline" nativeButton={false} render={<Link href={`/customers/${lead.converted_customer_id}`} />}>
                  مشاهده پرونده مشتری
                </Button>
              </CardContent>
            </Card>
          ) : null}
          {lead.description ? (
            <Card>
              <CardHeader>
                <CardTitle>توضیحات</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-line text-sm leading-7">{lead.description}</CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>سابقه پیگیری‌ها</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              تماس‌ها، یادداشت‌ها و فعالیت‌ها پس از ساخت بخش «فعالیت‌ها» اینجا نمایش داده می‌شوند.
            </CardContent>
          </Card>
        </div>

        <Card className="order-first h-fit lg:order-last">
          <CardHeader>
            <CardTitle>اطلاعات تماس</CardTitle>
          </CardHeader>
          <CardContent>
            <InfoRow icon={<Phone className="size-4" />} label="موبایل">
              <span className="ltr-value">{formatMobile(lead.mobile)}</span>
            </InfoRow>
            <InfoRow icon={<AtSign className="size-4" />} label="ایمیل">
              <span className="ltr-value break-all">{lead.email ?? "—"}</span>
            </InfoRow>
            <InfoRow icon={<Building2 className="size-4" />} label="شرکت">
              {lead.company_name ?? "—"}
            </InfoRow>
            <InfoRow icon={<UserRound className="size-4" />} label="مسئول">
              <Owner user={lead.owner} />
            </InfoRow>
            <InfoRow icon={<Link2 className="size-4" />} label="منبع">
              {lead.source?.name ?? "—"}
            </InfoRow>
            <InfoRow icon={<CalendarDays className="size-4" />} label="تاریخ ثبت">
              {formatDate(lead.created_at)}
            </InfoRow>
            <InfoRow icon={<Tag className="size-4" />} label="برچسب‌ها">
              {lead.tags.length ? (
                <span className="flex flex-wrap justify-end gap-1">
                  {lead.tags.map((t) => (
                    <Badge key={t.id} variant="secondary" className="bg-accent text-accent-foreground">
                      {t.name}
                    </Badge>
                  ))}
                </span>
              ) : (
                "—"
              )}
            </InfoRow>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function StatusCard({ lead }: { lead: LeadFull }) {
  const queryClient = useQueryClient();
  const [choosingDisqualify, setChoosingDisqualify] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  async function update(status: LeadStatus, disqualifyReason?: string) {
    setPending(true);
    try {
      await apiFetch(`/leads/${lead.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, disqualify_reason: disqualifyReason ?? null }),
      });
      await queryClient.invalidateQueries({ queryKey: keys.leads });
      setChoosingDisqualify(false);
      setReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>وضعیت پیگیری</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="وضعیت">
          {EDITABLE_STATUSES.map((s) => {
            const active = lead.status === s;
            return (
              <Button
                key={s}
                role="radio"
                aria-checked={active}
                variant={active ? "default" : "outline"}
                size="sm"
                disabled={pending}
                onClick={() => (s === "disqualified" ? setChoosingDisqualify(true) : void update(s))}
                className={cn(active && "pointer-events-none")}
              >
                {LEAD_STATUS_LABELS[s]}
              </Button>
            );
          })}
        </div>
        {lead.status === "disqualified" && lead.disqualify_reason ? (
          <p className="text-sm text-muted-foreground">دلیل: {lead.disqualify_reason}</p>
        ) : null}
        {choosingDisqualify ? (
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void update("disqualified", reason);
            }}
          >
            <Input
              autoFocus
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="دلیل نامناسب بودن"
              aria-label="دلیل نامناسب بودن"
              className="max-w-sm"
            />
            <Button type="submit" size="sm" variant="destructive" disabled={!reason.trim() || pending}>
              ثبت
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setChoosingDisqualify(false)}>
              انصراف
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
