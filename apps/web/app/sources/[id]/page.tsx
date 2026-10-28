import Link from "next/link";

import { Badge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import {
  retireSourceAction,
  runSourceAction,
  testSourceAction,
  updateSourceAction,
} from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, formatJson, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function SourceDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const [source, runs] = await Promise.all([api.source(id), api.sourceRuns(id)]);

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <p className="small muted">
            <Link href="/sources">Sources</Link> / {label(source.kind)}
          </p>
          <h1>{source.name}</h1>
          <p className="muted">
            <a href={source.root_url} rel="noreferrer noopener" target="_blank">
              {source.root_url}
            </a>
          </p>
          <div className="pill-row">
            <Badge
              tone={
                source.health === "healthy"
                  ? "ok"
                  : source.health === "failing"
                    ? "bad"
                    : "warn"
              }
            >
              {label(source.health)}
            </Badge>
            <Badge>{label(source.approval_status)}</Badge>
            <Badge>Legal: {label(source.legal_review_status)}</Badge>
            <Badge>{source.enabled ? "Enabled" : "Disabled"}</Badge>
          </div>
        </div>
        <div className="actions">
          <form action={testSourceAction}>
            <input type="hidden" name="id" value={source.id} />
            <button type="submit">Test preview</button>
          </form>
          <form action={runSourceAction}>
            <input type="hidden" name="id" value={source.id} />
            <button className="primary" type="submit" disabled={!source.enabled}>
              Run now
            </button>
          </form>
          <form action={retireSourceAction}>
            <input type="hidden" name="id" value={source.id} />
            <button className="danger" type="submit">
              Retire
            </button>
          </form>
        </div>
      </div>

      <div className="detail-grid">
        <div className="stack">
          <section className="card">
            <h2>Recent runs</h2>
            {runs.items.length === 0 ? (
              <p className="muted">No runs recorded yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Started</th>
                      <th>Status</th>
                      <th>Seen</th>
                      <th>Created</th>
                      <th>Updated</th>
                      <th>Scan</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.items.map((run) => (
                      <tr key={run.id}>
                        <td>{dateLabel(run.started_at)}</td>
                        <td>{label(run.status)}</td>
                        <td>{run.records_seen}</td>
                        <td>{run.records_created}</td>
                        <td>{run.records_updated}</td>
                        <td>{run.scan_complete ? "Complete" : "Partial"}</td>
                        <td>{run.error ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h2>Adapter configuration</h2>
            <pre>{formatJson(source.config_json)}</pre>
            <h3>Rate limits</h3>
            <pre>{formatJson(source.rate_limit_json)}</pre>
          </section>
        </div>

        <aside className="stack">
          <section className="card">
            <h2>Edit source</h2>
            <form action={updateSourceAction} className="stack">
              <input type="hidden" name="id" value={source.id} />
              <label>
                Name
                <input name="name" defaultValue={source.name} required maxLength={200} />
              </label>
              <label>
                Officialness
                <select name="officialness" defaultValue={source.officialness}>
                  <option value="official">Official</option>
                  <option value="credible_aggregator">Credible aggregator</option>
                  <option value="unknown">Unknown</option>
                </select>
              </label>
              <label>
                Approval
                <select name="approval_status" defaultValue={source.approval_status}>
                  <option value="candidate">Candidate</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="retired">Retired</option>
                </select>
              </label>
              <label>
                Legal review
                <select name="legal_review_status" defaultValue={source.legal_review_status}>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </label>
              <label>
                Interval hours
                <input
                  name="interval_hours"
                  type="number"
                  min={1}
                  max={8760}
                  defaultValue={source.interval_hours}
                />
              </label>
              <label>
                Schedule cron
                <input name="schedule_cron" defaultValue={source.schedule_cron ?? ""} maxLength={64} />
              </label>
              <label className="check">
                <input name="enabled" type="checkbox" defaultChecked={source.enabled} /> Enabled
              </label>
              <button className="primary" type="submit">
                Save source
              </button>
            </form>
          </section>

          <section className="card">
            <h2>Health</h2>
            <div className="meta">
              <span>Consecutive failures: {source.consecutive_failures}</span>
              <span>Last attempt: {dateLabel(source.last_attempt_at)}</span>
              <span>Last success: {dateLabel(source.last_success_at)}</span>
              <span>Next due: {dateLabel(source.next_due_at)}</span>
            </div>
            {source.last_error ? <p className="error">{source.last_error}</p> : null}
          </section>
        </aside>
      </div>
    </>
  );
}
