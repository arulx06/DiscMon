"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiSend } from "./api";
import { api } from "./api";
import type { RuntimeSchedule } from "./types";

export type RuntimeScheduleResult =
  | { ok: true; schedule: RuntimeSchedule }
  | { ok: false; message: string }
  | { ok: false; conflict: true; schedule: RuntimeSchedule | null; message: string };

export async function loadRuntimeScheduleAction(): Promise<RuntimeScheduleResult> {
  try {
    return { ok: true, schedule: await api.runtimeSchedule() };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.message
          : "Could not load the saved runtime schedule. Check the API connection and retry.",
    };
  }
}

export async function saveRuntimeScheduleAction(input: {
  revision: number;
  start_time: string;
  shutdown_time: string;
}): Promise<RuntimeScheduleResult> {
  try {
    const schedule = await apiSend<RuntimeSchedule>("/runtime-schedule", "PUT", input);
    revalidatePath("/settings");
    return { ok: true, schedule };
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      const latest = await loadRuntimeScheduleAction();
      return {
        ok: false,
        conflict: true,
        schedule: latest.ok ? latest.schedule : null,
        message: latest.ok
          ? "This schedule changed elsewhere. The latest saved values have been loaded; review them before saving again."
          : `This schedule changed elsewhere, but the latest values could not be loaded. ${latest.message}`,
      };
    }
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.message
          : "Could not save the runtime schedule. Check the API connection and retry.",
    };
  }
}

function text(form: FormData, key: string): string {
  const value = form.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function list(form: FormData, key: string): string[] {
  return text(form, key)
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function numberOrUndefined(form: FormData, key: string): number | undefined {
  const raw = text(form, key);
  if (!raw) {
    return undefined;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function withMessage(path: string, message: string, error = false): string {
  const separator = path.includes("?") ? "&" : "?";
  const key = error ? "error" : "notice";
  return `${path}${separator}${key}=${encodeURIComponent(message.slice(0, 300))}`;
}

async function mutation(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body: unknown,
  returnPath: string,
  successMessage: string,
): Promise<never> {
  let failure: string | null = null;
  try {
    await apiSend(path, method, body);
  } catch (error) {
    failure =
      error instanceof ApiError
        ? error.message
        : "The request failed before reaching the API";
  }
  if (failure) {
    redirect(withMessage(returnPath, failure, true));
  }
  revalidatePath("/", "layout");
  redirect(withMessage(returnPath, successMessage));
}

export async function reviewOpportunityAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  const decision = text(form, "decision");
  const note = text(form, "note");
  const followupRaw = text(form, "followup_due_at");
  await mutation(
    `/opportunities/${id}/review`,
    "POST",
    {
      decision,
      note: note || null,
      next_action: text(form, "next_action") || null,
      followup_due_at: followupRaw ? new Date(followupRaw).toISOString() : null,
    },
    `/opportunities/${id}`,
    "Review saved",
  );
}

export async function rescoreOpportunityAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(
    `/opportunities/${id}/rescore`,
    "POST",
    {},
    `/opportunities/${id}`,
    "Rescoring queued",
  );
}

export async function generateDigestAction(form: FormData): Promise<void> {
  const kind = text(form, "kind") || "daily";
  await mutation(
    `/digests/generate?kind=${encodeURIComponent(kind)}`,
    "POST",
    {},
    "/digests",
    `${kind === "weekly" ? "Weekly" : "Daily"} digest generated`,
  );
}

export async function reviewDigestAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(
    `/digests/${id}/reviewed`,
    "POST",
    {},
    `/digests/${id}`,
    "Digest marked reviewed",
  );
}

export async function updateProfileAction(form: FormData): Promise<void> {
  const body = {
    employment_stage: text(form, "employment_stage"),
    student_status: form.get("student_status") === "on",
    home_country: text(form, "home_country"),
    preferred_countries: list(form, "preferred_countries"),
    relocation_allowed: form.get("relocation_allowed") === "on",
    categories: list(form, "categories"),
    skills: list(form, "skills"),
    ignore_terms: list(form, "ignore_terms"),
    desired_yoe_min: numberOrUndefined(form, "desired_yoe_min"),
    desired_yoe_max: numberOrUndefined(form, "desired_yoe_max"),
    quiet_hours_start: numberOrUndefined(form, "quiet_hours_start"),
    quiet_hours_end: numberOrUndefined(form, "quiet_hours_end"),
    timezone: text(form, "timezone"),
    alert_channels: list(form, "alert_channels"),
    max_immediate_alerts_per_week: numberOrUndefined(
      form,
      "max_immediate_alerts_per_week",
    ),
  };
  await mutation("/profile", "PATCH", body, "/settings", "Preferences saved");
}

export async function createSourceAction(form: FormData): Promise<void> {
  let config: unknown = {};
  const rawConfig = text(form, "config_json");
  if (rawConfig) {
    try {
      config = JSON.parse(rawConfig);
    } catch {
      redirect(withMessage("/sources", "Configuration must be valid JSON", true));
    }
  }
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    redirect(withMessage("/sources", "Configuration must be a JSON object", true));
  }
  let sourceId = "";
  try {
    const created = await apiSend<{ id: string }>("/sources", "POST", {
      name: text(form, "name"),
      source_kind: text(form, "source_kind"),
      root_url: text(form, "root_url"),
      config_json: config,
      officialness: text(form, "officialness") || "unknown",
      enabled: form.get("enabled") === "on",
      approval_status: text(form, "approval_status") || "candidate",
      legal_review_status: text(form, "legal_review_status") || "pending",
      interval_hours: numberOrUndefined(form, "interval_hours") ?? 24,
      schedule_cron: text(form, "schedule_cron") || null,
    });
    sourceId = created.id;
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "Source creation failed";
    redirect(withMessage("/sources", message, true));
  }
  revalidatePath("/", "layout");
  redirect(withMessage(`/sources/${sourceId}`, "Source created"));
}

export async function updateSourceAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  let config: unknown = {};
  const rawConfig = text(form, "config_json");
  if (rawConfig) {
    try {
      config = JSON.parse(rawConfig);
    } catch {
      redirect(withMessage(`/sources/${id}`, "Configuration must be valid JSON", true));
    }
  }
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    redirect(withMessage(`/sources/${id}`, "Configuration must be a JSON object", true));
  }
  const body = {
    name: text(form, "name"),
    officialness: text(form, "officialness"),
    enabled: form.get("enabled") === "on",
    approval_status: text(form, "approval_status"),
    legal_review_status: text(form, "legal_review_status"),
    interval_hours: numberOrUndefined(form, "interval_hours"),
    schedule_cron: text(form, "schedule_cron") || null,
    config_json: config,
  };
  await mutation(`/sources/${id}`, "PATCH", body, `/sources/${id}`, "Source updated");
}

export async function testSourceAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  let message = "Preview completed";
  let error = false;
  try {
    const result = await apiSend<{
      ok: boolean;
      records_seen: number;
      scan_complete: boolean;
      error_class: string | null;
      message?: string;
    }>(`/sources/${id}/test`, "POST", {});
    message = result.ok
      ? `Preview: ${result.records_seen} records, ${result.scan_complete ? "complete scan" : "partial scan"}`
      : `Preview failed: ${result.error_class ?? result.message ?? "unknown error"}`;
    error = !result.ok;
  } catch (failure) {
    error = true;
    message = failure instanceof ApiError ? failure.message : "Preview failed";
  }
  revalidatePath("/", "layout");
  redirect(withMessage(`/sources/${id}`, message, error));
}

export async function runSourceAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(`/sources/${id}/run`, "POST", {}, `/sources/${id}`, "Run queued");
}

export async function retireSourceAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(
    `/sources/${id}`,
    "DELETE",
    {},
    `/sources/${id}`,
    "Source retired",
  );
}

export async function inspectUrlAction(form: FormData): Promise<void> {
  const body = {
    url: text(form, "url"),
    notes: text(form, "notes") || null,
  };
  await mutation(
    "/discovery/inspect-url",
    "POST",
    body,
    "/discover",
    "URL added to discovery candidates",
  );
}

export async function runDiscoveryAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(
    `/discovery/sources/${id}/run`,
    "POST",
    {},
    `/sources/${id}`,
    "Discovery scan queued",
  );
}

export async function promoteDiscoveryAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  let sourceId = "";
  try {
    const result = await apiSend<{ source_id: string; created: boolean }>(
      `/discovery/candidates/${id}/promote`,
      "POST",
      {},
    );
    sourceId = result.source_id;
  } catch (failure) {
    const message =
      failure instanceof ApiError ? failure.message : "Candidate promotion failed";
    redirect(withMessage("/discover", message, true));
  }
  revalidatePath("/", "layout");
  redirect(withMessage(`/sources/${sourceId}`, "Source created from candidate; review legal status before enabling"));
}

export async function decideDiscoveryAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  const decision = text(form, "decision");
  await mutation(
    `/discovery/candidates/${id}/decision`,
    "POST",
    { decision, notes: text(form, "notes") || null },
    "/discover",
    `Candidate ${decision}`,
  );
}

export async function retryJobAction(form: FormData): Promise<void> {
  const id = text(form, "id");
  await mutation(
    `/admin/jobs/${id}/retry`,
    "POST",
    {},
    "/health",
    "Job queued for retry",
  );
}
