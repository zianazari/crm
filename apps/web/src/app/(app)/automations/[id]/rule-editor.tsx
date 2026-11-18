"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import { CheckCircle2, CloudOff, FlaskConical, Loader2, Pause, Play, Rocket } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Breadcrumb, DetailError, DetailSkeleton } from "@/components/crm/detail-parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { subjectOf, type Graph, type Problem, type RepeatPolicy, type RuleDetail } from "@/lib/automation";
import { formatDateTime, formatNumber, toAsciiDigits } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Builder } from "../builder";
import { ExecutionHistory, VersionList } from "../history";
import { RuleStatusBadge } from "../parts";
import { TestDialog } from "../test-dialog";

type Meta = { name: string; description: string; repeat_policy: RepeatPolicy; max_runs_per_hour: number };
type SaveState = "saved" | "dirty" | "saving" | "error";
type Tab = "design" | "runs" | "versions";

const TABS: { key: Tab; label: string }[] = [
  { key: "design", label: "طراحی" },
  { key: "runs", label: "سابقه اجرا" },
  { key: "versions", label: "نسخه‌ها" },
];

export function RuleEditor({ id }: { id: string }) {
  const { data: rule, error } = useQuery({
    queryKey: ["automations", id],
    queryFn: () => apiFetch<RuleDetail>(`/automations/${id}`),
    staleTime: Infinity, // the editor owns the draft once it is open
  });
  if (error) return <DetailError error={error} />;
  if (!rule) return <DetailSkeleton />;
  return (
    <ReactFlowProvider>
      <Editor initial={rule} />
    </ReactFlowProvider>
  );
}

function Editor({ initial }: { initial: RuleDetail }) {
  const queryClient = useQueryClient();
  const [rule, setRule] = useState(initial);
  const [problems, setProblems] = useState<Problem[]>(initial.problems);
  const [meta, setMeta] = useState<Meta>({
    name: initial.name,
    description: initial.description ?? "",
    repeat_policy: initial.repeat_policy,
    max_runs_per_hour: initial.max_runs_per_hour,
  });
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [tab, setTab] = useState<Tab>("design");
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState<"publish" | "pause" | "resume" | null>(null);
  const [subject, setSubject] = useState(() => subjectOf(initial.draft.nodes.find((n) => n.kind === "trigger")?.config));

  const graphRef = useRef<Graph>(initial.draft);
  const metaRef = useRef(meta);
  const dirty = useRef(false);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const accept = useCallback(
    (detail: RuleDetail) => {
      setRule(detail);
      setProblems(detail.problems);
      queryClient.setQueryData(["automations", detail.id], detail);
      void queryClient.invalidateQueries({ queryKey: ["automations", "list"] });
    },
    [queryClient],
  );

  /** Saves the draft if anything changed; resolves to false when saving failed. */
  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    while (inFlight.current) await inFlight.current;
    if (!dirty.current) return true;
    dirty.current = false;
    setSaveState("saving");
    const body = { ...metaRef.current, description: metaRef.current.description || null, graph: graphRef.current };
    inFlight.current = apiFetch<RuleDetail>(`/automations/${initial.id}/draft`, { method: "PUT", body: JSON.stringify(body) })
      .then((detail) => {
        accept(detail);
        if (!dirty.current) setSaveState("saved");
        return true;
      })
      .catch((err: unknown) => {
        dirty.current = true;
        setSaveState("error");
        toast.error(err instanceof ApiError ? err.message : "ذخیره پیش‌نویس انجام نشد.");
        return false;
      })
      .finally(() => {
        inFlight.current = null;
      });
    return inFlight.current;
  }, [accept, initial.id]);

  const schedule = useCallback(() => {
    dirty.current = true;
    setSaveState("dirty");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), 1000);
  }, [flush]);

  const onGraphChange = useCallback(
    (graph: Graph) => {
      graphRef.current = graph;
      setSubject(subjectOf(graph.nodes.find((n) => n.kind === "trigger")?.config));
      schedule();
    },
    [schedule],
  );

  function updateMeta(patch: Partial<Meta>) {
    const next = { ...metaRef.current, ...patch };
    metaRef.current = next;
    setMeta(next);
    if (next.name.trim().length >= 2) schedule();
  }

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty.current || inFlight.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      // Leaving the page inside the app: save what is pending.
      if (dirty.current) void flush();
    };
  }, [flush]);

  async function action(kind: "publish" | "pause" | "resume") {
    setBusy(kind);
    try {
      if (!(await flush())) return;
      const detail = await apiFetch<RuleDetail>(`/automations/${initial.id}/${kind}`, { method: "POST" });
      accept(detail);
      void queryClient.invalidateQueries({ queryKey: ["automations", initial.id, "versions"] });
      toast.success(
        kind === "publish"
          ? `نسخه ${formatNumber(detail.active_version?.number ?? 0)} منتشر و فعال شد.`
          : kind === "pause"
            ? "اتوماسیون متوقف شد؛ اجراهای در انتظار لغو شدند."
            : "اتوماسیون دوباره فعال شد.",
      );
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as { detail?: { problems?: Problem[] } })?.detail : undefined;
      if (detail && typeof detail === "object" && Array.isArray(detail.problems)) {
        setProblems(detail.problems);
        setTab("design");
        toast.error("پیش از انتشار، ایرادهای مشخص‌شده روی بلوک‌ها را برطرف کنید.");
      } else {
        toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
      }
    } finally {
      setBusy(null);
    }
  }

  const canPublish = rule.status !== "active" || rule.unpublished_changes || saveState !== "saved";

  const ruleSettings = (
    <div className="space-y-4">
      <h2 className="font-semibold">تنظیمات اتوماسیون</h2>
      <Field label="نام" htmlFor="rule-name" required>
        <Input id="rule-name" maxLength={120} value={meta.name} onChange={(e) => updateMeta({ name: e.target.value })} />
      </Field>
      <Field label="توضیح" htmlFor="rule-description">
        <Textarea
          id="rule-description"
          rows={2}
          maxLength={1000}
          value={meta.description}
          onChange={(e) => updateMeta({ description: e.target.value })}
        />
      </Field>
      <Field label="تکرار برای یک پرونده" htmlFor="rule-repeat">
        <NativeSelect
          id="rule-repeat"
          className="w-full"
          value={meta.repeat_policy}
          onChange={(e) => updateMeta({ repeat_policy: e.target.value as RepeatPolicy })}
        >
          <NativeSelectOption value="every_time">با هر رویداد دوباره اجرا شود</NativeSelectOption>
          <NativeSelectOption value="once_per_record">برای هر پرونده فقط یک بار</NativeSelectOption>
        </NativeSelect>
      </Field>
      <Field label="سقف اجرا در هر ساعت" htmlFor="rule-cap" hint="جلوی ارسال یا ساخت انبوه ناخواسته را می‌گیرد.">
        <Input
          id="rule-cap"
          inputMode="numeric"
          value={String(meta.max_runs_per_hour)}
          onChange={(e) => {
            const n = Number.parseInt(toAsciiDigits(e.target.value), 10);
            updateMeta({ max_runs_per_hour: Number.isFinite(n) ? Math.min(Math.max(n, 1), 10000) : 1 });
          }}
        />
      </Field>
      <div className="space-y-1 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
        <p className="font-medium text-foreground">کار با صفحه‌کلید</p>
        <p>با Tab بین بلوک‌ها بروید و با Enter یکی را انتخاب کنید؛ کلیدهای جهت آن را جابه‌جا و Delete حذفش می‌کند.</p>
        <p>دکمه‌های پنل بلوک‌ها، بلوک تازه را بعد از بلوک انتخاب‌شده اضافه و وصل می‌کنند؛ «بلوک بعدی» در تنظیمات هر بلوک اتصال را تغییر می‌دهد.</p>
      </div>
    </div>
  );

  return (
    <>
      <div className="space-y-3">
        <Breadcrumb href="/automations" label="اتوماسیون" current={meta.name || rule.name} />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{meta.name || rule.name}</h1>
            <RuleStatusBadge status={rule.status} />
            {rule.active_version ? (
              <span className="text-sm text-muted-foreground">نسخه فعال {formatNumber(rule.active_version.number)}</span>
            ) : null}
            <SaveIndicator state={saveState} at={rule.draft_updated_at} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setTesting(true)}>
              <FlaskConical aria-hidden />
              اجرای آزمایشی
            </Button>
            {rule.status === "active" ? (
              <Button variant="outline" disabled={busy !== null} onClick={() => void action("pause")}>
                {busy === "pause" ? <Loader2 className="animate-spin" aria-hidden /> : <Pause aria-hidden />}
                توقف
              </Button>
            ) : rule.status === "paused" ? (
              <Button variant="outline" disabled={busy !== null} onClick={() => void action("resume")}>
                {busy === "resume" ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />}
                ادامه با نسخه {formatNumber(rule.active_version?.number ?? 0)}
              </Button>
            ) : null}
            <Button disabled={busy !== null || !canPublish} onClick={() => void action("publish")}>
              {busy === "publish" ? <Loader2 className="animate-spin" aria-hidden /> : <Rocket aria-hidden />}
              {rule.active_version ? "انتشار نسخه جدید" : "انتشار و فعال‌سازی"}
            </Button>
          </div>
        </div>
        {rule.status === "active" && rule.unpublished_changes ? (
          <p className="text-sm text-amber-800">
            تغییرهای پیش‌نویس هنوز منتشر نشده‌اند؛ نسخه {formatNumber(rule.active_version?.number ?? 0)} همچنان اجرا می‌شود.
          </p>
        ) : null}
      </div>

      <div className="flex w-fit gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="بخش‌های اتوماسیون">
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

      {/* The builder stays mounted so switching tabs keeps unsaved positions and selection. */}
      <div role="tabpanel" hidden={tab !== "design"}>
        <Builder initial={initial.draft} problems={problems} onChange={onGraphChange} ruleSettings={ruleSettings} />
      </div>
      {tab === "runs" ? <ExecutionHistory ruleId={rule.id} /> : null}
      {tab === "versions" ? <VersionList ruleId={rule.id} /> : null}

      <TestDialog open={testing} onOpenChange={setTesting} ruleId={rule.id} subject={subject} prepare={flush} />
    </>
  );
}

function SaveIndicator({ state, at }: { state: SaveState; at: string | null }) {
  if (state === "saving" || state === "dirty") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" aria-live="polite">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        در حال ذخیره پیش‌نویس…
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive" aria-live="polite">
        <CloudOff className="size-3.5" aria-hidden />
        ذخیره نشد؛ با تغییر بعدی دوباره تلاش می‌شود
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" aria-live="polite">
      <CheckCircle2 className="size-3.5" aria-hidden />
      پیش‌نویس ذخیره شد{at ? ` (${formatDateTime(at)})` : ""}
    </span>
  );
}
