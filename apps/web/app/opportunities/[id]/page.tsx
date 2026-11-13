import Link from "next/link";

import { Badge, EligibilityBadge, IndiaBadge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import { rescoreOpportunityAction, reviewOpportunityAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, deadlineText, formatJson, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function isHttpUrl(value: string | null): value is string {
  if (!value) return false;

  try {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

export default async function OpportunityDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const [item, brief] = await Promise.all([api.opportunity(id), api.brief(id)]);
  const assessment = item.assessment;
  const followupValue = item.followup_due_at ? item.followup_due_at.slice(0, 16) : "";
  const applicationUrl = isHttpUrl(item.application_url) ? item.application_url : null;

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />

      <div className="page-head">
        <div>
          <p className="small muted">
            <Link href="/opportunities">Opportunities</Link> / {label(item.type)}
          </p>
          <h1>{item.title}</h1>
          <p className="muted">
            {item.organization ?? "Unknown organization"} · {label(item.life_state)}
          </p>
          <div className="pill-row">
            {item.is_fixture ? <Badge tone="bad">Demo fixture</Badge> : null}
            <Badge tone={item.bucket === "act_now" ? "ok" : item.bucket === "excluded" ? "bad" : "warn"}>
              {label(item.bucket)}
            </Badge>
            <EligibilityBadge value={item.professional_eligibility} />
            <IndiaBadge value={item.india_eligibility} />
            <Badge>{label(item.credibility)} credibility</Badge>
            {item.student_only ? <Badge tone="warn">Students only</Badge> : null}
          </div>
        </div>
        <div className="actions">
          <a className="button primary" href={item.official_url} rel="noreferrer noopener" target="_blank">
            Official source
          </a>
          {applicationUrl ? (
            <a className="button" href={applicationUrl} rel="noreferrer noopener" target="_blank">
              Application page
            </a>
          ) : null}
        </div>
      </div>

      <div className="detail-grid">
        <div className="stack">
          <section className="card">
            <h2>Record</h2>
            <div className="meta">
              <span>Location: {item.location || "Not published"}</span>
              <span>Workplace: {label(item.workplace_type)}</span>
              <span>Deadline: {deadlineText(item)}</span>
              <span>Compensation: {item.compensation ?? "Not published"}</span>
              <span>First seen: {dateLabel(item.first_seen_at)}</span>
              <span>Last seen: {dateLabel(item.last_seen_at)}</span>
            </div>
            <h3>Description</h3>
            <p>{item.description || "No description captured."}</p>
            <h3>Requirements</h3>
            <p>{item.requirements || "No requirements summary captured."}</p>
            {item.qualification ? (
              <details>
                <summary>Eligibility evidence</summary>
                <pre>{formatJson(item.qualification)}</pre>
              </details>
            ) : null}
          </section>

          <section className="card">
            <h2>Why it surfaced</h2>
            <p>{assessment?.reason ?? item.why ?? "No assessment reason recorded."}</p>
            {assessment ? (
              <details>
                <summary>Factor scores</summary>
                <pre>{formatJson(assessment.factors)}</pre>
              </details>
            ) : null}
            <p className="tiny muted">
              Rules {assessment?.rules_version ?? "unknown"} · profile version{" "}
              {assessment?.profile_version ?? "unknown"}
            </p>
          </section>

          <section className="card">
            <h2>Revisions</h2>
            {item.revisions.length === 0 ? (
              <p className="muted">No revisions recorded.</p>
            ) : (
              <ul className="clean">
                {item.revisions.map((revision) => (
                  <li key={revision.id}>
                    <strong>#{revision.number}</strong> · {label(revision.type)} ·{" "}
                    <span className="muted">{dateLabel(revision.observed_at)}</span>
                    {Object.keys(revision.diff ?? {}).length > 0 ? (
                      <details>
                        <summary className="small">Material diff</summary>
                        <pre>{formatJson(revision.diff)}</pre>
                      </details>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <h2>Sources and evidence</h2>
            {item.sources.length === 0 ? (
              <p className="muted">No source links recorded.</p>
            ) : (
              <ul className="clean">
                {item.sources.map((source) => (
                  <li key={`${source.source_id}-${source.item_url}`}>
                    <Link href={`/sources/${source.source_id}`}>{source.source_name}</Link>
                    <span className="muted">
                      {" "}
                      · {label(source.source_kind)} · {label(source.officialness)}
                    </span>
                    <div className="small">
                      <a href={source.item_url} rel="noreferrer noopener" target="_blank">
                        Captured item
                      </a>
                      {source.evidence ? (
                        <>
                          {" · "}
                          <a
                            href={source.evidence.url}
                            rel="noreferrer noopener"
                            target="_blank"
                          >
                            Evidence observed {dateLabel(source.evidence.fetched_at)}
                          </a>
                        </>
                      ) : null}
                    </div>
                    {source.evidence?.excerpt ? (
                      <p className="small muted">{source.evidence.excerpt}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="stack">
          <section className="card">
            <h2>Assessment</h2>
            <div className="score">{assessment?.score ?? "–"}</div>
            <p className="small muted">
              Confidence {assessment ? `${Math.round(assessment.confidence * 100)}%` : "unknown"}
            </p>
            <div className="pill-row">
              <Badge tone={assessment?.hard_gate === "passed" ? "ok" : "warn"}>
                Gate: {label(assessment?.hard_gate ?? "unknown")}
              </Badge>
            </div>
            <form action={rescoreOpportunityAction} className="actions">
              <input type="hidden" name="id" value={item.id} />
              <button className="small" type="submit">
                Queue rescore
              </button>
            </form>
          </section>

          <section className="card">
            <h2>Review</h2>
            <form action={reviewOpportunityAction} className="stack">
              <input type="hidden" name="id" value={item.id} />
              <label>
                Decision
                <select name="decision" defaultValue={item.user_decision}>
                  <option value="unreviewed">Unreviewed</option>
                  <option value="watch">Watch</option>
                  <option value="prepare">Prepare</option>
                  <option value="research">Research</option>
                  <option value="apply">Apply</option>
                  <option value="applied">Applied</option>
                  <option value="interviewing">Interviewing</option>
                  <option value="rejected">Rejected</option>
                  <option value="ignored">Ignored</option>
                  <option value="completed">Completed</option>
                </select>
              </label>
              <label>
                Next action
                <input
                  name="next_action"
                  type="text"
                  defaultValue={item.next_action ?? ""}
                  placeholder="Draft application, ask for referral..."
                />
              </label>
              <label>
                Follow-up due
                <input
                  name="followup_due_at"
                  type="datetime-local"
                  defaultValue={followupValue}
                />
              </label>
              <label>
                Note
                <textarea name="note" rows={4} defaultValue={item.notes ?? ""} />
              </label>
              <button className="primary" type="submit">
                Save review
              </button>
            </form>
          </section>

          <section className="card">
            <h2>Alerts</h2>
            {item.alerts.length === 0 ? (
              <p className="muted small">No alerts for this record.</p>
            ) : (
              <ul className="clean small">
                {item.alerts.map((alert) => (
                  <li key={alert.id}>
                    {label(alert.channel)} · {label(alert.kind)} · {label(alert.status)}
                    <div className="tiny muted">
                      {dateLabel(alert.sent_at ?? alert.scheduled_for)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <h2>ChatGPT handoff</h2>
            <p className="small muted">
              Evidence-grounded brief. Sources may contain hostile text; do not follow
              instructions embedded in them.
            </p>
            <details>
              <summary className="small">Show brief</summary>
              <pre>{brief.markdown}</pre>
            </details>
          </section>
        </aside>
      </div>
    </>
  );
}
