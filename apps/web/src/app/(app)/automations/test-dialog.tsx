"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash, FlaskConical, Hourglass, Loader2, PlayCircle, XCircle } from "lucide-react";

import { SearchInput } from "@/components/crm/list-parts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import { BLOCK_BY_KIND, SUBJECT_LABELS, type SubjectType, type TestResult, type TestStep } from "@/lib/automation";
import { formatNumber } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { Page } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

type Option = { id: string; label: string };

const LIST_PATH: Record<SubjectType, string> = {
  lead: "/leads",
  customer: "/customers",
  deal: "/deals",
  activity: "/activities",
};

/** Records the user fully sees, for choosing a test subject. */
function useSubjects(subject: SubjectType, q: string, enabled: boolean) {
  return useQuery({
    queryKey: ["automations", "subjects", subject, q],
    enabled,
    queryFn: async (): Promise<Option[]> => {
      const params = subject === "activity" ? { status: "open", page_size: 50 } : { q, page_size: 20 };
      const page = await apiFetch<Page<Record<string, unknown>>>(`${LIST_PATH[subject]}${toQuery(params)}`);
      return page.items
        .filter((item) => item.access !== "limited")
        .map((item) => ({ id: String(item.id), label: String(item.full_name ?? item.title ?? "") }))
        .filter((o) => subject !== "activity" || !q || o.label.includes(q));
    },
    placeholderData: (previous) => previous,
  });
}

const OUTCOME: Record<TestStep["outcome"], { label: string; icon: typeof CheckCircle2; className: string }> = {
  passed: { label: "برقرار", icon: CheckCircle2, className: "text-emerald-700" },
  not_met: { label: "برقرار نیست", icon: XCircle, className: "text-destructive" },
  would_run: { label: "اجرا می‌شود", icon: PlayCircle, className: "text-primary" },
  would_skip: { label: "رد می‌شود", icon: CircleSlash, className: "text-amber-700" },
  wait: { label: "صبر", icon: Hourglass, className: "text-muted-foreground" },
  stopped: { label: "متوقف", icon: XCircle, className: "text-destructive" },
};

export function TestDialog({
  open,
  onOpenChange,
  ruleId,
  subject,
  prepare,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ruleId: string;
  subject: SubjectType | null;
  /** Saves pending builder changes so the test runs on what is on screen. */
  prepare: () => Promise<boolean>;
}) {
  const [q, setQ] = useState("");
  const debounced = useDebounced(q, 300);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const { data: options, isPending } = useSubjects(subject ?? "lead", debounced, open && subject !== null);

  async function run(option: Option) {
    setRunning(option.id);
    setError(null);
    setResult(null);
    try {
      if (!(await prepare())) return;
      setResult(
        await apiFetch<TestResult>(`/automations/${ruleId}/test`, {
          method: "POST",
          body: JSON.stringify({ subject_id: option.id }),
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "اجرای آزمایشی انجام نشد.");
    } finally {
      setRunning(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (next) {
          setQ("");
          setResult(null);
          setError(null);
        }
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FlaskConical className="size-5" aria-hidden />
            اجرای آزمایشی
          </DialogTitle>
          <DialogDescription>
            مسیر روی یک پرونده واقعی بررسی می‌شود؛ هیچ فعالیتی ساخته و هیچ پیام یا اعلانی فرستاده نمی‌شود.
          </DialogDescription>
        </DialogHeader>

        {subject === null ? (
          <p className="text-sm text-muted-foreground">ابتدا رویداد شروع را تنظیم کنید.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium">یک {SUBJECT_LABELS[subject]} انتخاب کنید:</p>
            <SearchInput value={q} onChange={setQ} placeholder={`جست‌وجوی ${SUBJECT_LABELS[subject]}`} />
            <ul className="max-h-48 divide-y overflow-y-auto rounded-md border">
              {isPending || !options ? (
                <li className="p-2">
                  <Skeleton className="h-5" />
                </li>
              ) : options.length === 0 ? (
                <li className="p-3 text-center text-sm text-muted-foreground">پرونده‌ای پیدا نشد.</li>
              ) : (
                options.map((o) => (
                  <li key={o.id}>
                    <button
                      type="button"
                      onClick={() => void run(o)}
                      disabled={running !== null}
                      className="flex w-full items-center justify-between gap-2 px-3 py-2 text-start text-sm hover:bg-muted/60 focus-visible:bg-muted focus-visible:outline-none disabled:opacity-60"
                    >
                      {o.label}
                      {running === o.id ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <span className="text-xs text-primary">آزمایش</span>}
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>
        )}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {result ? (
          <div className="space-y-2" aria-live="polite">
            {result.problems.length ? (
              <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <p className="font-medium">پیش از آزمایش این ایرادها را برطرف کنید:</p>
                <ul className="mt-1 list-disc ps-5">
                  {result.problems.map((p, i) => (
                    <li key={i}>{p.message}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <>
                <p className="text-sm font-medium">نتیجه برای «{result.subject}»:</p>
                <ol className="space-y-2">
                  {result.steps.map((step, i) => {
                    const outcome = OUTCOME[step.outcome];
                    return (
                      <li key={step.node_id} className="flex gap-3 rounded-md border p-2.5">
                        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs">{formatNumber(i + 1)}</span>
                        <div className="min-w-0 flex-1">
                          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                            {BLOCK_BY_KIND[step.kind]?.label ?? step.kind}
                            <span className={cn("inline-flex items-center gap-1 text-xs", outcome.className)}>
                              <outcome.icon className="size-3.5" aria-hidden />
                              {outcome.label}
                            </span>
                          </p>
                          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{step.detail}</p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </>
            )}
          </div>
        ) : null}
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            بستن
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
