"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Archive,
  ArchiveRestore,
  AtSign,
  Building2,
  Link2,
  MessageSquare,
  Pencil,
  Phone,
  PhoneCall,
  Plus,
  Tag,
  Tags,
  UserRound,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AssignDialog } from "@/components/crm/assign-dialog";
import { InfoRow, Owner } from "@/components/crm/bits";
import { consentText } from "@/components/crm/consent-fields";
import { CustomerSupport } from "@/components/crm/customer-support";
import { CustomerFormDialog } from "@/components/crm/customer-form-dialog";
import { DealFormDialog } from "@/components/crm/deal-form-dialog";
import { DealStatusBadge } from "@/components/crm/deal-status";
import { Breadcrumb, DetailError, DetailSkeleton, LimitedRecord } from "@/components/crm/detail-parts";
import { OrganizationPicker } from "@/components/crm/organization-picker";
import { PlannedActivities, Timeline } from "@/components/crm/record-activity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { formatMobile, formatToman } from "@/lib/format";
import { canManage, keys, useCustomer, useDeals, useMe } from "@/lib/queries";
import { CHANNEL_LABELS, type CustomerFull, type Ref } from "@/lib/types";

export function CustomerDetail({ id }: { id: string }) {
  const { data: customer, isPending, error } = useCustomer(id);
  if (isPending) return <DetailSkeleton />;
  if (error) return <DetailError error={error} />;

  return (
    <div className="space-y-6">
      <Breadcrumb href="/customers" label="مشتریان" current={customer.full_name} />
      {customer.access === "full" ? (
        <FullCustomer customer={customer} />
      ) : (
        <LimitedRecord title={customer.full_name} owner={customer.owner} lastActivity={customer.last_activity_at} />
      )}
    </div>
  );
}

function FullCustomer({ customer }: { customer: CustomerFull }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const archived = Boolean(customer.archived_at);
  const primaryOrg = customer.organizations[0];

  async function post(path: string, message: string) {
    try {
      await apiFetch(`/customers/${customer.id}/${path}`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: keys.customers });
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
            <h1 className="text-2xl font-bold">{customer.full_name}</h1>
            {archived ? <Badge variant="outline">بایگانی‌شده</Badge> : null}
          </div>
          {primaryOrg ? (
            <p className="text-muted-foreground">
              {primaryOrg.job_title ? `${primaryOrg.job_title}، ` : null}
              {primaryOrg.organization.name}
            </p>
          ) : (
            <p className="text-muted-foreground">مشتری شخصی</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!archived ? (
            <CustomerFormDialog
              customer={customer}
              trigger={
                <Button variant="outline">
                  <Pencil aria-hidden />
                  ویرایش
                </Button>
              }
            />
          ) : null}
          {canManage(me?.role) ? (
            <>
              <AssignDialog
                path={`/customers/${customer.id}`}
                currentOwner={customer.owner}
                invalidate={keys.customers}
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
          <OrganizationsCard customer={customer} editable={!archived} />
          {customer.description ? (
            <Card>
              <CardHeader>
                <CardTitle>توضیحات</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-line text-sm leading-7">{customer.description}</CardContent>
            </Card>
          ) : null}
          <PlannedActivities
            subject={{ customer: { id: customer.id, name: customer.full_name } }}
            filter={{ customer_id: customer.id }}
          />
          <CustomerDeals customer={customer} />
          <CustomerSupport customer={customer} editable={!archived} />
          <Timeline subject={{ customer_id: customer.id }} />
        </div>

        <Card className="order-first h-fit lg:order-last">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserRound className="size-5" aria-hidden />
              خلاصه مشتری
            </CardTitle>
          </CardHeader>
          <CardContent>
            <InfoRow icon={<UserRound className="size-4" />} label="مالک پرونده">
              <Owner user={customer.owner} />
            </InfoRow>
            <InfoRow icon={<Phone className="size-4" />} label="موبایل">
              <span className="ltr-value">{formatMobile(customer.mobile)}</span>
            </InfoRow>
            <InfoRow icon={<PhoneCall className="size-4" />} label="تلفن">
              <span className="ltr-value">{customer.phone ?? "—"}</span>
            </InfoRow>
            <InfoRow icon={<AtSign className="size-4" />} label="ایمیل">
              <span className="ltr-value break-all">{customer.email ?? "—"}</span>
            </InfoRow>
            <InfoRow icon={<MessageSquare className="size-4" />} label="کانال ترجیحی">
              {customer.preferred_channel ? CHANNEL_LABELS[customer.preferred_channel] : "—"}
            </InfoRow>
            <InfoRow icon={<MessageSquare className="size-4" />} label="اجازه دریافت پیام">
              {consentText(customer)}
            </InfoRow>
            <InfoRow icon={<Link2 className="size-4" />} label="منبع">
              {customer.source?.name ?? "—"}
            </InfoRow>
            <InfoRow icon={<Tag className="size-4" />} label="برچسب‌ها">
              {customer.tags.length ? (
                <span className="flex flex-wrap justify-end gap-1">
                  {customer.tags.map((t) => (
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

function OrganizationsCard({ customer, editable }: { customer: CustomerFull; editable: boolean }) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [organization, setOrganization] = useState<Ref | null>(null);
  const [jobTitle, setJobTitle] = useState("");

  async function run(request: Promise<unknown>) {
    try {
      await request;
      await queryClient.invalidateQueries({ queryKey: keys.customers });
      setAdding(false);
      setOrganization(null);
      setJobTitle("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Building2 className="size-5" aria-hidden />
          سازمان‌ها
        </CardTitle>
        {editable && !adding ? (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            افزودن
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {customer.organizations.length === 0 && !adding ? (
          <p className="text-sm text-muted-foreground">این مشتری به سازمانی متصل نیست.</p>
        ) : null}
        <ul className="divide-y">
          {customer.organizations.map((link) => (
            <li key={link.organization.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                <span className="font-medium">{link.organization.name}</span>
                {link.job_title ? <span className="text-muted-foreground"> — {link.job_title}</span> : null}
              </span>
              {editable ? (
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`حذف اتصال به ${link.organization.name}`}
                  onClick={() =>
                    void run(
                      apiFetch(`/customers/${customer.id}/organizations/${link.organization.id}`, {
                        method: "DELETE",
                      }),
                    )
                  }
                >
                  <X />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        {adding ? (
          <div className="space-y-2 rounded-lg border p-3">
            <OrganizationPicker value={organization} onChange={setOrganization} />
            <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="سمت (اختیاری)" />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!organization}
                onClick={() =>
                  void run(
                    apiFetch(`/customers/${customer.id}/organizations`, {
                      method: "POST",
                      body: JSON.stringify({ organization_id: organization!.id, job_title: jobTitle || null }),
                    }),
                  )
                }
              >
                ذخیره
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                انصراف
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Deals of this customer. Others' deals appear in limited form only (spec 4.3:
 * opening one deal does not reveal the details of the customer's other deals). */
function CustomerDeals({ customer }: { customer: CustomerFull }) {
  const { data } = useDeals({ customer_id: customer.id, page_size: 50 });
  const deals = data?.items ?? [];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Tags className="size-5" aria-hidden />
          فروش‌ها
        </CardTitle>
        {!customer.archived_at ? (
          <DealFormDialog
            customer={customer}
            trigger={
              <Button size="sm" variant="outline">
                <Plus aria-hidden />
                فروش جدید
              </Button>
            }
          />
        ) : null}
      </CardHeader>
      <CardContent>
        {deals.length === 0 ? (
          <p className="text-sm text-muted-foreground">هنوز فروشی برای این مشتری ثبت نشده است.</p>
        ) : (
          <ul className="divide-y">
            {deals.map((deal) => {
              const amount =
                deal.access === "full" ? (deal.status === "won" ? deal.contract_amount : deal.amount) : null;
              return (
                <li key={deal.id}>
                  <Link
                    href={`/deals/${deal.id}`}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm hover:text-primary"
                  >
                    <span className="font-medium">{deal.title}</span>
                    <span className="flex items-center gap-3">
                      {amount !== null ? <span>{formatToman(amount)}</span> : null}
                      <DealStatusBadge deal={deal} />
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
