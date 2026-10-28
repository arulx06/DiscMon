import { eligibilityTone, label } from "@/lib/format";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "ok" | "warn" | "bad";
}) {
  return <span className={`badge ${tone === "neutral" ? "" : tone}`}>{children}</span>;
}

export function EligibilityBadge({ value }: { value: string }) {
  return <Badge tone={eligibilityTone(value)}>Professional: {label(value)}</Badge>;
}

export function IndiaBadge({ value }: { value: string }) {
  return <Badge tone={eligibilityTone(value)}>India: {label(value)}</Badge>;
}
