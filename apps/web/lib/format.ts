export function label(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }
  return value.replaceAll("_", " ");
}

export function dateLabel(value: string | null | undefined): string {
  if (!value) {
    return "Not published";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    ...(value.includes("T") ? { timeStyle: "short" as const } : {}),
  }).format(parsed);
}

export function eligibilityTone(value: string): "ok" | "warn" | "bad" {
  if (value === "verified_yes" || value === "not_applicable") {
    return "ok";
  }
  if (value === "verified_no") {
    return "bad";
  }
  return "warn";
}

export function deadlineText(item: {
  deadline_on: string | null;
  deadline_at: string | null;
  deadline_precision: string;
}): string {
  if (item.deadline_precision === "exact" && item.deadline_at) {
    return dateLabel(item.deadline_at);
  }
  if (item.deadline_precision === "date_only" && item.deadline_on) {
    return `${item.deadline_on} (date only, no cutoff time)`;
  }
  if (item.deadline_precision === "month_only" && item.deadline_on) {
    return `${item.deadline_on.slice(0, 7)} (month only)`;
  }
  return "Not published";
}

export function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
