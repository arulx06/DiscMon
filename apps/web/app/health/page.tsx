import Link from "next/link";

import { Badge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import { retryJobAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function HealthPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const [status, health, jobs, alerts] = await Promise.all([
    api.systemStatus(),
    api.sourceHealth(),
    api.jobs(),
    api.alerts(),
  ]);

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <h1>Operations</h1>
          <p className="muted">
            Failures stay visible. A failed scan is never rendered as “no opportunities”.
          </p>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <strong>{status.database}</strong>
          <span>Database</span>
        </div>
        <div className="stat">
          <strong>{health.total}</strong>
          <span>Sources</span>
        </div>
        <div className="stat">
          <strong>{status.active_jobs}</strong>
          <span>Active jobs</span>
        </div>
        <div className="stat">
          <strong>{alerts.items.length}</strong>
          <span>Recent alerts</span>
        </div>
      </div>

      <h2>Source health</h2>
      <div className="grid">
        {Object.entries(health.counts).map(([key, count]) => (
          <div className="stat" key={key}>
            <strong>{count}</strong>
            <span>{label(key)}</span>
          </div>
        ))}
      </div>
      {health.attention.length === 0 ? (
        <div className="card empty">No sources need attention.</div>
      ) : (
        <div className="table-wrap" style={{ marginTop: 14 }}>
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Health</th>
                <th>Last error</th>
                <th>Last success</th>
              </tr>
            </thead>
            <tbody>
              {health.attention.map((source) => (
                <tr key={source.id}>
                  <td>
                    <Link href={`/sources/${source.id}`}>{source.name}</Link>
                  </td>
                  <td>
                    <Badge tone={source.health === "failing" ? "bad" : "warn"}>
                      {label(source.health)}
                    </Badge>
                  </td>
                  <td>{source.last_error ?? "—"}</td>
                  <td>{dateLabel(source.last_success_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Recent jobs</h2>
      {jobs.items.length === 0 ? (
        <div className="card empty">No jobs recorded.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kind</th>
                <th>State</th>
                <th>Attempts</th>
                <th>Available</th>
                <th>Error</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {jobs.items.map((job) => (
                <tr key={job.id}>
                  <td>{label(job.kind)}</td>
                  <td>
                    <Badge
                      tone={
                        job.state === "succeeded"
                          ? "ok"
                          : job.state === "dead"
                            ? "bad"
                            : "warn"
                      }
                    >
                      {label(job.state)}
                    </Badge>
                  </td>
                  <td>{job.attempts}</td>
                  <td>{dateLabel(job.available_at)}</td>
                  <td>{job.last_error ?? "—"}</td>
                  <td>
                    {job.state === "dead" || job.state === "retry_wait" ? (
                      <form action={retryJobAction}>
                        <input type="hidden" name="id" value={job.id} />
                        <button className="small" type="submit">
                          Retry
                        </button>
                      </form>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Recent alerts</h2>
      {alerts.items.length === 0 ? (
        <div className="card empty">No alerts recorded.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Created</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {alerts.items.map((alert) => (
                <tr key={alert.id}>
                  <td>{label(alert.channel)}</td>
                  <td>{label(alert.kind)}</td>
                  <td>
                    <Badge
                      tone={
                        alert.status === "sent"
                          ? "ok"
                          : alert.status === "failed"
                            ? "bad"
                            : "warn"
                      }
                    >
                      {label(alert.status)}
                    </Badge>
                  </td>
                  <td>{dateLabel(alert.created_at)}</td>
                  <td>{alert.error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
