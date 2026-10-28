import Link from "next/link";

import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const dashboard = await api.dashboard();
  const jobs = Object.entries(dashboard.jobs);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Radar overview</h1>
          <p className="muted">
            Evidence-first counts. A failed scan is shown as a failure, never as zero
            opportunities.
          </p>
        </div>
        <Link className="button primary" href="/opportunities">
          Review opportunities
        </Link>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <strong>{dashboard.active_opportunities}</strong>
          <span>Active opportunities</span>
        </div>
        <div className="stat">
          <strong>{dashboard.pending_alerts}</strong>
          <span>Pending alerts</span>
        </div>
        <div className="stat">
          <strong>{dashboard.failing_sources.length}</strong>
          <span>Failing sources</span>
        </div>
        <div className="stat">
          <strong>{jobs.reduce((total, [, count]) => total + count, 0)}</strong>
          <span>Queued jobs</span>
        </div>
      </div>

      {dashboard.scan_is_partial ? (
        <div className="error" role="alert">
          Scan coverage is partial because at least one source is failing. Results below
          are not a complete picture.
        </div>
      ) : (
        <div className="notice">No failing sources are currently reported.</div>
      )}

      <div className="grid">
        <section className="card">
          <h2>Recommendation buckets</h2>
          {Object.keys(dashboard.buckets).length === 0 ? (
            <p className="muted">No assessed opportunities yet.</p>
          ) : (
            <ul className="clean">
              {Object.entries(dashboard.buckets).map(([bucket, count]) => (
                <li key={bucket}>
                  <Link href={`/opportunities?bucket=${bucket}`}>
                    {label(bucket)}
                  </Link>
                  <span className="muted"> · {count}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <h2>Source health</h2>
          {Object.keys(dashboard.source_health).length === 0 ? (
            <p className="muted">No sources configured.</p>
          ) : (
            <ul className="clean">
              {Object.entries(dashboard.source_health).map(([health, count]) => (
                <li key={health}>
                  <span className={`badge ${health === "healthy" ? "ok" : health === "failing" ? "bad" : "warn"}`}>
                    {label(health)}
                  </span>
                  <span className="muted"> · {count}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="actions">
            <Link className="button small" href="/sources">
              Manage sources
            </Link>
            <Link className="button small" href="/health">
              Operations
            </Link>
          </div>
        </section>
      </div>

      <h2>Sources needing attention</h2>
      {dashboard.failing_sources.length === 0 ? (
        <div className="card empty">No failing sources.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Failures</th>
                <th>Last error</th>
                <th>Last failure</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.failing_sources.map((source) => (
                <tr key={source.id}>
                  <td>
                    <Link href={`/sources/${source.id}`}>{source.name}</Link>
                  </td>
                  <td>{source.consecutive_failures}</td>
                  <td>{source.last_error ?? "No details recorded"}</td>
                  <td>{dateLabel(source.last_error_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Recent failed runs</h2>
      {dashboard.recent_failed_runs.length === 0 ? (
        <div className="card empty">No failed runs recorded.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Started</th>
                <th>Category</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.recent_failed_runs.map((run) => (
                <tr key={run.id}>
                  <td>{run.source}</td>
                  <td>{dateLabel(run.started_at)}</td>
                  <td>{label(run.error_category)}</td>
                  <td>{run.error ?? "Redacted"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
