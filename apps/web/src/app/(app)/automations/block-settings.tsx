"use client";

import type { ReactNode } from "react";

import { Field } from "@/components/crm/bits";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import {
  CONDITION_FIELD_LABELS,
  DELAY_UNIT_LABELS,
  EVENT_LABELS,
  PLACEHOLDER_HINT,
  SUBJECT_LABELS,
  fieldsFor,
  type BlockConfig,
  type BlockKind,
  type SubjectType,
} from "@/lib/automation";
import { toAsciiDigits } from "@/lib/format";
import { useAssignableUsers } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS } from "@/lib/types";
import { RECIPIENTS, useConditionOptions, useQueueTeams } from "./parts";

type Props = {
  nodeId: string;
  kind: BlockKind;
  config: BlockConfig;
  subject: SubjectType | null;
  onChange: (config: BlockConfig) => void;
};

function int(value: string): number {
  const n = Number.parseInt(toAsciiDigits(value), 10);
  return Number.isFinite(n) ? n : 0;
}

function Select({
  id,
  value,
  onChange,
  options,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  placeholder?: string;
}) {
  return (
    <NativeSelect id={id} className="w-full" value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined ? <NativeSelectOption value="">{placeholder}</NativeSelectOption> : null}
      {options.map(([v, label]) => (
        <NativeSelectOption key={v} value={v}>
          {label}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}

function UserSelect({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  const { data: users = [] } = useAssignableUsers();
  return (
    <Select
      id={id}
      value={value}
      onChange={onChange}
      placeholder="انتخاب کاربر"
      options={users.map((u) => [u.id, u.full_name])}
    />
  );
}

function TeamSelect({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  const { data: teams = [] } = useQueueTeams();
  return (
    <Select
      id={id}
      value={value}
      onChange={onChange}
      placeholder={teams.length ? "انتخاب تیم" : "تیم مالی فعالی تعریف نشده است"}
      options={teams.map((t) => [t.id, t.name])}
    />
  );
}

/** The settings form of the selected block (spec 4.6). The API validates everything again. */
export function BlockSettings({ nodeId, kind, config, subject, onChange }: Props) {
  const set = (patch: BlockConfig) => onChange({ ...config, ...patch });
  const id = (name: string) => `${nodeId}-${name}`;
  const str = (key: string) => String(config[key] ?? "");

  let body: ReactNode = null;
  switch (kind) {
    case "trigger":
      body = (
        <>
          <Field label="رویداد" htmlFor={id("event")} required>
            <Select
              id={id("event")}
              value={str("event")}
              onChange={(event) =>
                onChange({
                  event,
                  ...(event === "record.assigned" ? { entity_type: "lead" } : {}),
                  ...(event === "deal.inactive" ? { days: 3 } : {}),
                })
              }
              options={Object.entries(EVENT_LABELS)}
            />
          </Field>
          {config.event === "record.assigned" ? (
            <Field label="نوع پرونده" htmlFor={id("entity")} required>
              <Select
                id={id("entity")}
                value={str("entity_type")}
                onChange={(entity_type) => set({ entity_type })}
                options={(["lead", "customer", "deal"] as const).map((k) => [k, SUBJECT_LABELS[k]])}
              />
            </Field>
          ) : null}
          {config.event === "deal.inactive" ? (
            <Field label="تعداد روز بدون فعالیت" htmlFor={id("days")} required hint="بین ۱ تا ۳۶۵ روز.">
              <Input
                id={id("days")}
                inputMode="numeric"
                value={str("days")}
                onChange={(e) => set({ days: int(e.target.value) })}
              />
            </Field>
          ) : null}
          {config.event === "deal.stage_entered" ? (
            <p className="text-xs leading-5 text-muted-foreground">
              فقط وقتی اجرا می‌شود که فروش واقعاً از مرحله دیگری وارد شود. مرحله را با یک بلوک «شرط» مشخص کنید.
            </p>
          ) : null}
        </>
      );
      break;
    case "condition":
      body = <ConditionSettings nodeId={nodeId} config={config} subject={subject} onChange={onChange} />;
      break;
    case "create_activity":
      body = (
        <>
          <Field label="نوع فعالیت" htmlFor={id("type")} required>
            <Select
              id={id("type")}
              value={str("activity_type")}
              onChange={(activity_type) => set({ activity_type })}
              options={Object.entries(ACTIVITY_TYPE_LABELS)}
            />
          </Field>
          <Field label="عنوان" htmlFor={id("title")} required hint={PLACEHOLDER_HINT}>
            <Input id={id("title")} maxLength={200} value={str("title")} onChange={(e) => set({ title: e.target.value })} />
          </Field>
          <Field label="توضیحات" htmlFor={id("description")}>
            <Textarea
              id={id("description")}
              rows={2}
              value={str("description")}
              onChange={(e) => set({ description: e.target.value })}
            />
          </Field>
          <Field label="موعد (چند روز بعد)" htmlFor={id("due")} hint="صفر یعنی همان روز.">
            <Input
              id={id("due")}
              inputMode="numeric"
              value={str("due_in_days")}
              onChange={(e) => set({ due_in_days: int(e.target.value) })}
            />
          </Field>
          <Field label="مسئول انجام" htmlFor={id("assignee")} required>
            <Select
              id={id("assignee")}
              value={str("assignee")}
              onChange={(assignee) =>
                set({
                  assignee,
                  ...(assignee === "user" ? {} : { user_id: undefined }),
                  ...(assignee === "team" ? {} : { team_id: undefined }),
                })
              }
              options={[
                ["record_owner", "مسئول پرونده"],
                ["user", "کاربر مشخص"],
                ["team", "صف تیم مالی (یکی از اعضا برمی‌دارد)"],
              ]}
            />
          </Field>
          {config.assignee === "user" ? (
            <Field label="کاربر" htmlFor={id("user")} required>
              <UserSelect id={id("user")} value={str("user_id")} onChange={(user_id) => set({ user_id })} />
            </Field>
          ) : null}
          {config.assignee === "team" ? (
            <Field
              label="تیم"
              htmlFor={id("team")}
              required
              hint="کار در صف تیم می‌ماند تا عضوی آن را بردارد یا مدیر تیم واگذار کند. اگر تیم غیرفعال یا بی‌عضو باشد، اجرا متوقف و به شما اعلام می‌شود."
            >
              <TeamSelect id={id("team")} value={str("team_id")} onChange={(team_id) => set({ team_id })} />
            </Field>
          ) : null}
        </>
      );
      break;
    case "notify":
      body = (
        <>
          <Field label="گیرنده" htmlFor={id("recipient")} required>
            <Select
              id={id("recipient")}
              value={str("recipient")}
              onChange={(recipient) => set({ recipient, ...(recipient === "user" ? {} : { user_id: undefined }) })}
              options={Object.entries(RECIPIENTS)}
            />
          </Field>
          {config.recipient === "user" ? (
            <Field label="کاربر" htmlFor={id("user")} required>
              <UserSelect id={id("user")} value={str("user_id")} onChange={(user_id) => set({ user_id })} />
            </Field>
          ) : null}
          <Field label="عنوان اعلان" htmlFor={id("title")} required hint={PLACEHOLDER_HINT}>
            <Input id={id("title")} maxLength={200} value={str("title")} onChange={(e) => set({ title: e.target.value })} />
          </Field>
          <Field label="متن" htmlFor={id("body")}>
            <Textarea id={id("body")} rows={2} value={str("body")} onChange={(e) => set({ body: e.target.value })} />
          </Field>
        </>
      );
      break;
    case "send_sms":
      body = (
        <>
          <Field label="متن پیامک" htmlFor={id("text")} required hint={PLACEHOLDER_HINT}>
            <Textarea id={id("text")} rows={4} maxLength={500} value={str("text")} onChange={(e) => set({ text: e.target.value })} />
          </Field>
          <ConsentNote channel="پیامک" />
        </>
      );
      break;
    case "send_email":
      body = (
        <>
          <Field label="موضوع" htmlFor={id("subject")} required>
            <Input id={id("subject")} maxLength={200} value={str("subject")} onChange={(e) => set({ subject: e.target.value })} />
          </Field>
          <Field label="متن ایمیل" htmlFor={id("text")} required hint={PLACEHOLDER_HINT}>
            <Textarea id={id("text")} rows={6} value={str("text")} onChange={(e) => set({ text: e.target.value })} />
          </Field>
          <ConsentNote channel="ایمیل" />
        </>
      );
      break;
    case "delay":
      body = (
        <div className="grid grid-cols-2 gap-3">
          <Field label="مدت" htmlFor={id("amount")} required>
            <Input
              id={id("amount")}
              inputMode="numeric"
              value={str("amount")}
              onChange={(e) => set({ amount: int(e.target.value) })}
            />
          </Field>
          <Field label="واحد" htmlFor={id("unit")} required>
            <Select id={id("unit")} value={str("unit")} onChange={(unit) => set({ unit })} options={Object.entries(DELAY_UNIT_LABELS)} />
          </Field>
          <p className="col-span-2 text-xs leading-5 text-muted-foreground">
            حداکثر ۹۰ روز. پس از تأخیر، شرط‌های قبلی، اجازه مخاطب و فعال‌بودن اتوماسیون دوباره بررسی می‌شوند.
          </p>
        </div>
      );
      break;
  }
  return <div className="space-y-4">{body}</div>;
}

function ConsentNote({ channel }: { channel: string }) {
  return (
    <p className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
      {channel} فقط برای مخاطبی فرستاده می‌شود که اجازه دریافت داده باشد؛ اجازه در زمان ارسال بررسی می‌شود.
    </p>
  );
}

function ConditionSettings({
  nodeId,
  config,
  subject,
  onChange,
}: Omit<Props, "kind">) {
  const field = String(config.field ?? "");
  const options = useConditionOptions(field);
  const values = Array.isArray(config.values) ? (config.values as string[]) : [];
  const fields = fieldsFor(subject);

  return (
    <>
      <Field label="ویژگی" htmlFor={`${nodeId}-field`} required>
        <Select
          id={`${nodeId}-field`}
          value={field}
          placeholder="انتخاب ویژگی"
          onChange={(next) => onChange({ ...config, field: next, values: [] })}
          options={fields.map((f) => [f, CONDITION_FIELD_LABELS[f]])}
        />
      </Field>
      <Field label="مقایسه" htmlFor={`${nodeId}-op`} required>
        <Select
          id={`${nodeId}-op`}
          value={String(config.operator ?? "in")}
          onChange={(operator) => onChange({ ...config, operator })}
          options={[
            ["in", "یکی از موارد زیر باشد"],
            ["not_in", "هیچ‌کدام از موارد زیر نباشد"],
          ]}
        />
      </Field>
      {field ? (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">
            مقدارها<span className="text-destructive" aria-hidden> *</span>
          </legend>
          {options.length === 0 ? (
            <p className="text-xs text-muted-foreground">موردی برای انتخاب تعریف نشده است.</p>
          ) : (
            <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-md border p-2">
              {options.map((o) => (
                <label key={o.value} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={values.includes(o.value)}
                    onChange={(e) =>
                      onChange({
                        ...config,
                        values: e.target.checked ? [...values, o.value] : values.filter((v) => v !== o.value),
                      })
                    }
                  />
                  {o.label}
                </label>
              ))}
            </div>
          )}
        </fieldset>
      ) : null}
    </>
  );
}
