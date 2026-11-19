"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Mail, Megaphone, MessageSquareText, Plus, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Pagination } from "@/components/crm/list-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { CHANNEL_LABELS, EMPTY_FILTERS, type Campaign, type CampaignPage, type Channel } from "@/lib/campaigns";
import { formatDateTime, formatNumber } from "@/lib/format";
import { canManage, toQuery, useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { CampaignStatusBadge, ProgressBar } from "./parts";
import { PolicyTab } from "./policy-tab";
import { SuppressionsTab } from "./suppressions-tab";
import { TemplatesTab } from "./templates-tab";

type Tab = "campaigns" | "templates" | "suppressions" | "policy";

const TABS: { key: Tab; label: string }[] = [
  { key: "campaigns", label: "کمپین‌ها" },
  { key: "templates", label: "قالب‌های پیام" },
  { key: "suppressions", label: "فهرست عدم ارسال" },
  { key: "policy", label: "قواعد ارسال" },
];

export function CampaignsView() {
  const { data: me, isPending } = useMe();
  const [tab, setTab] = useState<Tab>("campaigns");
  if (isPending || !me) return <Skeleton className="h-96" />;
  if (!canManage(me.role)) {
    return (
      <>
        <PageHeader title="کمپین‌ها" />
        <Alert>
          <ShieldAlert aria-hidden />
          <AlertTitle>دسترسی به کمپین ندارید</AlertTitle>
          <AlertDescription>ساخت و اجرای کمپین با مدیر فروش و ادمین است.</AlertDescription>
        </Alert>
      </>
    );
  }
  return (
    <>
      <PageHeader
        title="کمپین‌ها"
        description="پیامک و ایمیل تبلیغاتی به مخاطبانی که اجازه داده‌اند؛ با پیش‌نمایش، ارسال آزمایشی و نتیجه هر گیرنده."
        actions={tab === "campaigns" ? <NewCampaignDialog /> : null}
      />
      <div className="flex w-fit flex-wrap gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="بخش‌های کمپین">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm",
              tab === t.key ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "campaigns" ? <CampaignList /> : null}
      {tab === "templates" ? <TemplatesTab /> : null}
      {tab === "suppressions" ? <SuppressionsTab admin={me.role === "admin"} /> : null}
      {tab === "policy" ? <PolicyTab admin={me.role === "admin"} /> : null}
    </>
  );
}

function CampaignList() {
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: ["campaigns", "list", page],
    queryFn: () => apiFetch<CampaignPage>(`/campaigns${toQuery({ page, page_size: 20 })}`),
    placeholderData: (previous) => previous,
    refetchInterval: 15_000,
  });
  return (
    <>
      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>نام</TableHead>
                <TableHead>کانال</TableHead>
                <TableHead>وضعیت</TableHead>
                <TableHead className="w-56">گیرندگان</TableHead>
                <TableHead>سازنده</TableHead>
                <TableHead>آخرین تغییر</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending || !data ? (
                Array.from({ length: 3 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6}>
                      <Skeleton className="h-5" />
                    </TableCell>
                  </TableRow>
                ))
              ) : data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-14 text-center">
                    <Megaphone className="mx-auto mb-3 size-8 text-muted-foreground" aria-hidden />
                    <p className="font-medium">هنوز کمپینی نساخته‌اید</p>
                    <p className="mt-1 text-sm text-muted-foreground">با «کمپین جدید» یک پیش‌نویس بسازید؛ تا اجرا چیزی فرستاده نمی‌شود.</p>
                  </TableCell>
                </TableRow>
              ) : (
                data.items.map((c: Campaign) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Link href={`/campaigns/${c.id}`} className="font-medium hover:underline">
                        {c.name}
                      </Link>
                    </TableCell>
                    <TableCell>{CHANNEL_LABELS[c.channel]}</TableCell>
                    <TableCell>
                      <CampaignStatusBadge status={c.status} />
                    </TableCell>
                    <TableCell>
                      {c.stats.total ? (
                        <div className="space-y-1">
                          <ProgressBar stats={c.stats} />
                          <p className="text-xs text-muted-foreground">
                            {formatNumber(c.stats.delivered + c.stats.accepted)} از {formatNumber(c.stats.total)} فرستاده
                          </p>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">پس از اجرا</span>
                      )}
                    </TableCell>
                    <TableCell>{c.created_by.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(c.updated_at)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && data.total > data.page_size ? (
        <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      ) : null}
    </>
  );
}

function NewCampaignDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<Channel>("sms");
  const [pending, setPending] = useState(false);

  async function create() {
    setPending(true);
    try {
      const campaign = await apiFetch<Campaign>("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          channel,
          body: "",
          audience: { kind: "segment", contacts: [], filters: EMPTY_FILTERS },
        }),
      });
      router.push(`/campaigns/${campaign.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ساخت کمپین انجام نشد.");
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setName("");
          setChannel("sms");
          setPending(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button>
            <Plus aria-hidden />
            کمپین جدید
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>کمپین جدید</DialogTitle>
          <DialogDescription>یک پیش‌نویس ساخته می‌شود؛ مخاطبان و متن را در صفحه بعد تعیین می‌کنید.</DialogDescription>
        </DialogHeader>
        <Field label="نام کمپین" htmlFor="campaign-name" required>
          <Input id="campaign-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </Field>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">کانال</legend>
          <div role="radiogroup" className="grid grid-cols-2 gap-2">
            {(["sms", "email"] as const).map((c) => {
              const Icon = c === "sms" ? MessageSquareText : Mail;
              return (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={channel === c}
                  onClick={() => setChannel(c)}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border p-3 text-sm hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
                    channel === c && "border-primary bg-accent/60 font-medium ring-1 ring-primary",
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {CHANNEL_LABELS[c]}
                </button>
              );
            })}
          </div>
        </fieldset>
        <DialogFooter>
          <Button onClick={() => void create()} disabled={pending || name.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ساخت پیش‌نویس
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
