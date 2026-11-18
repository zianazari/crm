/** Text for a record's message permission, e.g. on its detail page. */
export function consentText(record: { sms_consent: boolean; email_consent: boolean }): string {
  const allowed = [record.sms_consent && "پیامک", record.email_consent && "ایمیل"].filter(Boolean);
  return allowed.length ? allowed.join(" و ") : "اجازه نداده است";
}

/** Permission to receive automated SMS and email (spec 4.6: messages go out only with it). */
export function ConsentFields({
  sms,
  email,
  onChange,
  idPrefix,
}: {
  sms: boolean;
  email: boolean;
  onChange: (next: { sms: boolean; email: boolean }) => void;
  idPrefix: string;
}) {
  return (
    <fieldset className="space-y-2 sm:col-span-2">
      <legend className="text-sm font-medium">اجازه دریافت پیام</legend>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <label htmlFor={`${idPrefix}-sms-consent`} className="flex items-center gap-2">
          <input
            id={`${idPrefix}-sms-consent`}
            type="checkbox"
            className="size-4 accent-primary"
            checked={sms}
            onChange={(e) => onChange({ sms: e.target.checked, email })}
          />
          پیامک
        </label>
        <label htmlFor={`${idPrefix}-email-consent`} className="flex items-center gap-2">
          <input
            id={`${idPrefix}-email-consent`}
            type="checkbox"
            className="size-4 accent-primary"
            checked={email}
            onChange={(e) => onChange({ sms, email: e.target.checked })}
          />
          ایمیل
        </label>
      </div>
      <p className="text-xs text-muted-foreground">
        پیامک و ایمیل خودکار فقط وقتی فرستاده می‌شود که مخاطب اجازه داده باشد.
      </p>
    </fieldset>
  );
}
