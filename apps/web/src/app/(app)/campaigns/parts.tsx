"use client";

import { Badge } from "@/components/ui/badge";
import { CAMPAIGN_STATUS_LABELS, type CampaignStatus, type Stats } from "@/lib/campaigns";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const STYLES: Record<CampaignStatus, string> = {
  draft: "bg-secondary text-secondary-foreground",
  scheduled: "bg-sky-50 text-sky-800",
  running: "bg-amber-100 text-amber-900",
  paused: "bg-muted text-muted-foreground",
  completed: "bg-success text-success-foreground",
  failed: "bg-destructive/10 text-destructive",
};

export function CampaignStatusBadge({ status }: { status: CampaignStatus }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", STYLES[status])}>
      {CAMPAIGN_STATUS_LABELS[status]}
    </Badge>
  );
}

const SEGMENTS: { key: keyof Stats; label: string; className: string }[] = [
  { key: "delivered", label: "تحویل‌شده", className: "bg-emerald-600" },
  { key: "accepted", label: "پذیرفته‌شده", className: "bg-emerald-300" },
  { key: "in_queue", label: "در صف", className: "bg-sky-400" },
  { key: "pending", label: "در انتظار", className: "bg-stone-300" },
  { key: "failed", label: "ناموفق", className: "bg-red-500" },
  { key: "unknown", label: "نامشخص", className: "bg-amber-400" },
  { key: "skipped", label: "ارسال نشد", className: "bg-stone-200" },
];

/** Where each recipient stands, as one bar with a legend (identity is never color alone). */
export function ProgressBar({ stats, legend = false }: { stats: Stats; legend?: boolean }) {
  if (!stats.total) return <span className="text-xs text-muted-foreground">—</span>;
  const shown = SEGMENTS.filter((s) => stats[s.key] > 0);
  return (
    <div className="space-y-2">
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        {shown.map((s) => (
          <span key={s.key} className={cn("h-full", s.className)} style={{ width: `${(stats[s.key] / stats.total) * 100}%` }} />
        ))}
      </div>
      {legend ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {shown.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className={cn("size-2 rounded-full", s.className)} aria-hidden />
              {s.label}: <span className="font-medium text-foreground">{formatNumber(stats[s.key])}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="sr-only">
          {shown.map((s) => `${s.label} ${formatNumber(stats[s.key])}`).join("، ")}
        </p>
      )}
    </div>
  );
}
