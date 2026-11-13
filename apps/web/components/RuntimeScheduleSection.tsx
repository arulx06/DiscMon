"use client";

import { useState, useTransition } from "react";

import {
  loadRuntimeScheduleAction,
  saveRuntimeScheduleAction,
  type RuntimeScheduleResult,
} from "@/lib/actions";
import type { RuntimeSchedule } from "@/lib/types";

function minutesBetween(start: string, end: string): number | null {
  const time = /^(\d{2}):(\d{2})$/;
  const startMatch = time.exec(start);
  const endMatch = time.exec(end);
  if (!startMatch || !endMatch) return null;
  const startMinutes = Number(startMatch[1]) * 60 + Number(startMatch[2]);
  const endMinutes = Number(endMatch[1]) * 60 + Number(endMatch[2]);
  return endMinutes > startMinutes ? endMinutes - startMinutes : null;
}

function durationLabel(minutes: number | null): string {
  if (minutes === null) return "—";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

function validationMessage(start: string, shutdown: string): string | null {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(start) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(shutdown)) {
    return "Choose valid start and shutdown times.";
  }
  const duration = minutesBetween(start, shutdown);
  if (duration === null) return "Shutdown must be later than start on the same day.";
  if (duration < 60) return "The runtime window must be at least 60 minutes.";
  if (start > "20:00") return "Start time must be no later than 20:00 to preserve the backup window.";
  if (shutdown < "21:00") {
    return "Shutdown before 21:00 is not supported until the approved backup-timer migration is complete.";
  }
  return null;
}

function scheduleStatus(schedule: RuntimeSchedule): { label: string; detail: string } {
  const hostConfirmed =
    schedule.status === "applied" && schedule.applied_revision === schedule.revision;
  if (hostConfirmed) return { label: "Applied by host", detail: "The host confirmed this saved revision." };
  if (schedule.status === "error") {
    return { label: "Host sync error", detail: schedule.sync_error || "The host could not apply this schedule." };
  }
  if (schedule.status === "stale" || (schedule.status === "applied" && !hostConfirmed)) {
    return { label: "Host schedule is stale", detail: schedule.sync_error || "The host has not confirmed the latest saved revision." };
  }
  return { label: "Waiting for host confirmation", detail: "Saved changes are not active until the host confirms them." };
}

export function RuntimeScheduleSection({
  initialResult,
}: {
  initialResult: RuntimeScheduleResult;
}) {
  const initialSchedule = initialResult.ok ? initialResult.schedule : null;
  const [schedule, setSchedule] = useState<RuntimeSchedule | null>(initialSchedule);
  const [start, setStart] = useState(initialSchedule?.start_time ?? "");
  const [shutdown, setShutdown] = useState(initialSchedule?.shutdown_time ?? "");
  const [error, setError] = useState(initialResult.ok ? "" : initialResult.message);
  const [notice, setNotice] = useState("");
  const [isPending, startTransition] = useTransition();
  const validation = validationMessage(start, shutdown);
  const duration = minutesBetween(start, shutdown);
  const savedStatus = schedule ? scheduleStatus(schedule) : null;
  const changed = schedule !== null && (start !== schedule.start_time || shutdown !== schedule.shutdown_time);

  function applyLoadedSchedule(result: RuntimeScheduleResult) {
    if (result.ok) {
      setSchedule(result.schedule);
      setStart(result.schedule.start_time);
      setShutdown(result.schedule.shutdown_time);
      setError("");
      return;
    }
    if ("conflict" in result && result.schedule) {
      setSchedule(result.schedule);
      setStart(result.schedule.start_time);
      setShutdown(result.schedule.shutdown_time);
    }
    setError(result.message);
  }

  function refreshSchedule() {
    setNotice("");
    startTransition(async () => applyLoadedSchedule(await loadRuntimeScheduleAction()));
  }

  function saveSchedule() {
    if (!schedule || validation) return;
    setError("");
    setNotice("");
    startTransition(async () => {
      const result = await saveRuntimeScheduleAction({
        revision: schedule.revision,
        start_time: start,
        shutdown_time: shutdown,
      });
      if (result.ok) {
        setSchedule(result.schedule);
        setStart(result.schedule.start_time);
        setShutdown(result.schedule.shutdown_time);
        setNotice("Schedule saved. Host status reflects confirmation, not this save.");
        return;
      }
      applyLoadedSchedule(result);
      if (!("conflict" in result)) setError(result.message);
    });
  }

  return (
    <section className="card stack runtime-schedule" aria-labelledby="runtime-schedule-title">
      <div>
        <h2 id="runtime-schedule-title">Application Runtime Schedule</h2>
        <p className="muted">
          Choose when DiscMon application services run each day. This is separate from alert quiet hours.
        </p>
      </div>

      {error ? (
        <p className="runtime-message runtime-error" role="alert">{error}</p>
      ) : null}
      {notice ? (
        <p className="runtime-message runtime-success" role="status">{notice}</p>
      ) : null}

      {schedule ? (
        <>
          <div className="form-grid runtime-fields">
            <label>
              Daily start time
              <input
                aria-label="Daily start time"
                type="time"
                value={start}
                onChange={(event) => setStart(event.target.value)}
                disabled={isPending}
              />
            </label>
            <label>
              Daily shutdown time
              <input
                aria-label="Daily shutdown time"
                type="time"
                value={shutdown}
                onChange={(event) => setShutdown(event.target.value)}
                disabled={isPending}
              />
            </label>
            <div className="runtime-summary">
              <span className="muted">Timezone</span>
              <strong>{schedule.timezone}</strong>
            </div>
            <div className="runtime-summary">
              <span className="muted">Draft operating duration</span>
              <strong>{durationLabel(duration)}</strong>
            </div>
          </div>

          {validation ? <p className="runtime-message runtime-warning" role="status">{validation}</p> : null}

          <div className="runtime-saved" aria-live="polite">
            <h3>Current saved schedule</h3>
            <p>
              {schedule.start_time}–{schedule.shutdown_time} {schedule.timezone} · {durationLabel(schedule.duration_minutes)}
            </p>
            <h3>Host-applied schedule</h3>
            <p><strong>{savedStatus?.label}</strong> — {savedStatus?.detail}</p>
            {schedule.applied_start_time && schedule.applied_shutdown_time ? (
              <p>
                Host-confirmed: {schedule.applied_start_time}–{schedule.applied_shutdown_time} {schedule.timezone}
                {schedule.applied_revision !== null ? ` · revision ${schedule.applied_revision}` : ""}
              </p>
            ) : (
              <p className="muted">No host-applied schedule has been confirmed yet.</p>
            )}
            {schedule.last_sync_at ? <p className="small muted">Last host sync: {schedule.last_sync_at}</p> : null}
          </div>

          <div className="actions">
            <button className="primary" type="button" onClick={saveSchedule} disabled={isPending || !changed || Boolean(validation)}>
              {isPending ? "Saving…" : "Save schedule"}
            </button>
            <button type="button" onClick={refreshSchedule} disabled={isPending}>Refresh status</button>
          </div>
        </>
      ) : (
        <button type="button" onClick={refreshSchedule} disabled={isPending}>
          {isPending ? "Loading…" : "Retry loading schedule"}
        </button>
      )}

      <div className="runtime-guidance">
        <p>
          A shutdown before 21:00 is not supported while the existing 20:30 backup timer remains in place. Earlier shutdowns require an approved backup-timer migration.
        </p>
        <p>
          The laptop must be powered on and awake for scheduled start and shutdown. DiscMon is inaccessible while its application services are stopped.
        </p>
      </div>
    </section>
  );
}
