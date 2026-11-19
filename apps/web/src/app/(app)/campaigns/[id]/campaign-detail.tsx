"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, FlaskConical, Info, Loader2, Rocket, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Breadcrumb, DetailError, DetailSkeleton } from "@/components/crm/detail-parts";
import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { CHANNEL_LABELS, tehranInstant, type Audience, type Campaign, type Preview } from "@/lib/campaigns";
import { formatNumber, formatToman } from "@/lib/format";
import { todayIso } from "@/lib/jalali";
import { cn } from "@/lib/utils";
import { CampaignStatusBadge } from "../parts";
import { AudienceEditor } from "./audience-editor";
import { CampaignMonitor } from "./monitor";

export function useCampaign(id: string) {
  return useQuery({
    queryKey: ["campaigns", id],
    queryFn: () => apiFetch<Campaign>(`/campaigns/${id}`),
    refetchInterval: (query) => (["running", "scheduled"].includes(query.state.data?.status ?? "") ? 5_000 : false),
  });
}

export function CampaignDetail({ id }: { id: string }) {
  const { data: campaign, error } = useCampaign(id);
  if (error) return <DetailError error={error} />;
  if (!campaign) return <DetailSkeleton />;
  return (
    <>
      <Breadcrumb href="/campaigns" label="کمپین‌ها" current={campaign.name} />
      {campaign.status === "draft" ? (
        <DraftEditor key={campaign.version} campaign={campaign} />
      ) : (
        <CampaignMonitor campaign={campaign} />
      )}
    </>
  );
}

// -- draft -------------------------------------------------------------------------------

type Draft = Pick<Campaign, "name" | "channel" | "subject" | "body" | "audience">;

function DraftEditor({ campaign }: { campaign: Campaign }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>({
    name: campaign.name,
    channel: campaign.channel,
    subject: campaign.subject,
    body: campaign.body,
    audience: campaign.audience,
  });
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | "delete" | null>(null);
  const [starting, setStarting] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  /** Puts {name} where the cursor is (or at the end) and keeps the cursor after it. */
  function insertName() {
    const el = bodyRef.current;
    const at = el ? el.selectionStart : draft.body.length;
    const end = el ? el.selectionEnd : at;
    const body = `${draft.body.slice(0, at)}{name}${draft.body.slice(end)}`;
    set({ body });
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + 6, at + 6);
    });
  }
  const set = (patch: Partial<Draft>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setDirty(true);
  };
  const preview = useQuery({
    queryKey: ["campaigns", campaign.id, "preview", campaign.version],
    queryFn: () => apiFetch<Preview>(`/campaigns/${campaign.id}/preview`, { method: "POST" }),
  });

  /** Saves the draft; the new version re-renders this editor with fresh state. */
  async function save(quiet = false): Promise<Campaign | null> {
    if (!dirty) return campaign;
    setBusy("save");
    try {
      const saved = await apiFetch<Campaign>(`/campaigns/${campaign.id}`, {
        method: "PUT",
        body: JSON.stringify({ ...draft, version: campaign.version }),
      });
      queryClient.setQueryData(["campaigns", campaign.id], saved);
      void queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      if (!quiet) toast.success("پیش‌نویس ذخیره شد.");
      return saved;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ذخیره انجام نشد.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    if (!(await save(true))) return;
    setBusy("test");
    try {
      const { to } = await apiFetch<{ to: string }>(`/campaigns/${campaign.id}/test`, { method: "POST" });
      toast.success(`پیام آزمایشی به ${to} در صف ارسال قرار گرفت.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ارسال آزمایشی انجام نشد.");
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("delete");
    try {
      await apiFetch(`/campaigns/${campaign.id}`, { method: "DELETE" });
      void queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      router.push("/campaigns");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "حذف انجام نشد.");
      setBusy(null);
    }
  }

  const sms = draft.channel === "sms";
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{draft.name || campaign.name}</h1>
          <CampaignStatusBadge status={campaign.status} />
          <span className="text-sm text-muted-foreground">{CHANNEL_LABELS[draft.channel]}</span>
          {dirty ? <span className="text-xs text-amber-800">تغییرهای ذخیره‌نشده</span> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" className="text-destructive" disabled={busy !== null} onClick={() => void remove()}>
            <Trash2 aria-hidden />
            حذف
          </Button>
          <Button variant="outline" disabled={busy !== null || !dirty} onClick={() => void save()}>
            {busy === "save" ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
            ذخیره پیش‌نویس
          </Button>
          <Button variant="outline" disabled={busy !== null} onClick={() => void test()}>
            {busy === "test" ? <Loader2 className="animate-spin" aria-hidden /> : <FlaskConical aria-hidden />}
            ارسال آزمایشی به خودم
          </Button>
          <Button
            disabled={busy !== null}
            onClick={async () => {
              if (await save(true)) setStarting(true);
            }}
          >
            <Rocket aria-hidden />
            اجرا یا زمان‌بندی
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>پیام</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="نام کمپین" htmlFor="c-name" required>
                <Input id="c-name" maxLength={120} value={draft.name} onChange={(e) => set({ name: e.target.value })} />
              </Field>
              {!sms ? (
                <Field label="موضوع ایمیل" htmlFor="c-subject" required>
                  <Input id="c-subject" maxLength={200} value={draft.subject ?? ""} onChange={(e) => set({ subject: e.target.value })} />
                </Field>
              ) : null}
              <Field
                label={sms ? "متن پیامک" : "متن ایمیل"}
                htmlFor="c-body"
                required
                hint="{name} با نام هر مخاطب جایگزین می‌شود. پیوند لغو دریافت خودکار به انتهای پیام افزوده می‌شود."
              >
                <Textarea
                  ref={bodyRef}
                  id="c-body"
                  rows={sms ? 4 : 10}
                  maxLength={sms ? 1000 : 20000}
                  value={draft.body}
                  onChange={(e) => set({ body: e.target.value })}
                />
              </Field>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={insertName}
                >
                  درج نام مخاطب
                </Button>
                <span>{formatNumber(draft.body.length)} نویسه</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>مخاطبان</CardTitle>
            </CardHeader>
            <CardContent>
              <AudienceEditor value={draft.audience} onChange={(audience: Audience) => set({ audience })} />
            </CardContent>
          </Card>
        </div>
        <PreviewCard preview={preview.data} loading={preview.isFetching} dirty={dirty} onRefresh={() => void save()} sms={sms} />
      </div>
      {starting ? (
        <StartDialog campaign={campaign} preview={preview.data} onClose={() => setStarting(false)} />
      ) : null}
    </>
  );
}

function PreviewCard({
  preview,
  loading,
  dirty,
  onRefresh,
  sms,
}: {
  preview: Preview | undefined;
  loading: boolean;
  dirty: boolean;
  onRefresh: () => void;
  sms: boolean;
}) {
  return (
    <Card className="h-fit lg:sticky lg:top-20">
      <CardHeader>
        <CardTitle>پیش‌نمایش و برآورد</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {dirty ? (
          <div className="flex items-center justify-between gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
            پیش‌نمایش با آخرین ذخیره است.
            <Button size="sm" variant="outline" onClick={onRefresh}>
              ذخیره و به‌روزرسانی
            </Button>
          </div>
        ) : null}
        {!preview ? (
          <Skeleton className="h-48" />
        ) : (
          <div className={cn("space-y-4", loading && "opacity-60")}>
            <div>
              <p className="text-3xl font-bold">{formatNumber(preview.eligible)}</p>
              <p className="text-muted-foreground">
                گیرنده از {formatNumber(preview.contacts)} مخاطب در دامنه شما
              </p>
            </div>
            {Object.keys(preview.excluded).length ? (
              <div className="space-y-1">
                <p className="font-medium">ارسال نمی‌شود برای:</p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {Object.entries(preview.excluded).map(([reason, count]) => (
                    <li key={reason} className="flex justify-between gap-3">
                      <span>{reason.replace(/\.$/, "")}</span>
                      <span className="font-medium text-foreground">{formatNumber(count)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <dl className="space-y-1 border-t pt-3 text-xs">
              {sms && preview.parts ? (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">بخش‌های هر پیامک</dt>
                  <dd>{formatNumber(preview.parts)}</dd>
                </div>
              ) : null}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">برآورد هزینه</dt>
                <dd>{formatToman(preview.estimated_cost)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">ساعت مجاز ارسال</dt>
                <dd>{preview.window}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">سقف روزانه</dt>
                <dd>{formatNumber(preview.daily_limit)}</dd>
              </div>
              {preview.budget_left !== null ? (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">باقی‌مانده سقف ۳۰ روزه</dt>
                  <dd>{formatToman(preview.budget_left)}</dd>
                </div>
              ) : null}
            </dl>
            {preview.sample_text ? (
              <div className="space-y-1 border-t pt-3">
                <p className="text-xs text-muted-foreground">نمونه برای «{preview.sample_name}»:</p>
                {preview.sample_subject ? <p className="text-xs font-medium">موضوع: {preview.sample_subject}</p> : null}
                <p className="whitespace-pre-wrap break-words rounded-lg rounded-ss-none bg-accent px-3 py-2 text-[13px] leading-6 text-accent-foreground">
                  {/* The real link is per recipient; the preview's placeholder token is not. */}
                  {preview.sample_text.replace(/\/u\/0{48}/, "/u/…")}
                </p>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StartDialog({ campaign, preview, onClose }: { campaign: Campaign; preview: Preview | undefined; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [when, setWhen] = useState<"now" | "later">("now");
  const [date, setDate] = useState<string>(() => todayIso());
  const [time, setTime] = useState("10:00");
  const [pending, setPending] = useState(false);

  async function start() {
    setPending(true);
    try {
      const body = when === "later" ? { scheduled_at: tehranInstant(date, time) } : {};
      const saved = await apiFetch<Campaign>(`/campaigns/${campaign.id}/start`, { method: "POST", body: JSON.stringify(body) });
      queryClient.setQueryData(["campaigns", campaign.id], saved);
      void queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      toast.success(saved.status === "scheduled" ? "کمپین زمان‌بندی شد." : "کمپین اجرا شد؛ ارسال به‌تدریج انجام می‌شود.");
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "اجرا انجام نشد.");
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>اجرای کمپین «{campaign.name}»</DialogTitle>
          <DialogDescription>
            {preview
              ? `${formatNumber(preview.eligible)} گیرنده، برآورد هزینه ${formatToman(preview.estimated_cost)}.`
              : "در حال محاسبه گیرندگان…"}{" "}
            فهرست گیرندگان هنگام اجرا ثابت می‌شود و پیام ارسال‌شده قابل پس‌گرفتن نیست.
          </DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="زمان اجرا" className="grid grid-cols-2 gap-2">
          {(
            [
              ["now", "همین حالا", Rocket],
              ["later", "زمان‌بندی", CalendarClock],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={when === key}
              onClick={() => setWhen(key)}
              className={cn(
                "flex items-center gap-2 rounded-lg border p-3 text-sm hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
                when === key && "border-primary bg-accent/60 font-medium ring-1 ring-primary",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
        {when === "later" ? (
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
            <Field label="تاریخ" htmlFor="start-date">
              <JalaliDateInput id="start-date" value={date} onChange={(v) => v && setDate(v)} />
            </Field>
            <Field label="ساعت" htmlFor="start-time" hint="به وقت تهران">
              <Input id="start-time" type="time" dir="ltr" step={300} value={time} onChange={(e) => setTime(e.target.value)} />
            </Field>
          </div>
        ) : (
          <p className="flex items-start gap-2 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            اگر اکنون خارج از ساعت مجاز ارسال باشد، ارسال در بازه بعدی شروع می‌شود.
          </p>
        )}
        <DialogFooter>
          <Button onClick={() => void start()} disabled={pending || !preview || preview.eligible === 0}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {when === "now" ? "اجرا" : "زمان‌بندی"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
