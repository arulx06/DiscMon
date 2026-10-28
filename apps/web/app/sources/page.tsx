import Link from "next/link";

import { Badge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import { createSourceAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function SourcesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const sources = await api.sources();

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <h1>Sources</h1>
          <p className="muted">
            {sources.items.length} configured. Approval and legal review are required
            before a source can be enabled.
          </p>
        </div>
      </div>

      <details className="card" style={{ marginBottom: 18 }}>
        <summary>
          <strong>Add a source</strong>
        </summary>
        <form action={createSourceAction} className="form-grid" style={{ marginTop: 16 }}>
          <label>
            Name
            <input name="name" required maxLength={200} />
          </label>
          <label>
            Kind
            <select name="source_kind" defaultValue="ats_greenhouse">
              <option value="ats_greenhouse">Greenhouse</option>
              <option value="ats_lever">Lever</option>
              <option value="ats_ashby">Ashby</option>
              <option value="rss">RSS / Atom</option>
              <option value="github">GitHub releases</option>
              <option value="static_html">Static HTML</option>
              <option value="changedetection">changedetection.io</option>
              <option value="manual">Manual</option>
              <option value="newsletter">Newsletter</option>
            </select>
          </label>
          <label>
            Officialness
            <select name="officialness" defaultValue="official">
              <option value="official">Official</option>
              <option value="credible_aggregator">Credible aggregator</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label>
            Interval hours
            <input name="interval_hours" type="number" min={1} max={8760} defaultValue={24} />
          </label>
          <label className="wide">
            Root URL
            <input name="root_url" type="url" required placeholder="https://…" />
          </label>
          <label className="wide">
            Adapter configuration (JSON object)
            <textarea
              name="config_json"
              rows={5}
              defaultValue={'{\n  "board_token": "example",\n  "organization_name": "Example",\n  "organization_domain": "example.com"\n}'}
            />
          </label>
          <label>
            Approval
            <select name="approval_status" defaultValue="candidate">
              <option value="candidate">Candidate</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label>
            Legal review
            <select name="legal_review_status" defaultValue="pending">
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label>
            Schedule cron (optional)
            <input name="schedule_cron" maxLength={64} placeholder="0 8 * * *" />
          </label>
          <label className="check" style={{ alignSelf: "end" }}>
            <input name="enabled" type="checkbox" /> Enable immediately (requires
            approval)
          </label>
          <div className="wide">
            <button className="primary" type="submit">
              Create source
            </button>
          </div>
        </form>
      </details>

      {sources.items.length === 0 ? (
        <div className="card empty">No sources configured yet.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Kind</th>
                <th>Health</th>
                <th>Approval</th>
                <th>Last run</th>
                <th>Next due</th>
              </tr>
            </thead>
            <tbody>
              {sources.items.map((source) => (
                <tr key={source.id}>
                  <td>
                    <Link href={`/sources/${source.id}`}>{source.name}</Link>
                    <div className="tiny muted">{source.root_url}</div>
                  </td>
                  <td>{label(source.kind)}</td>
                  <td>
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
                  </td>
                  <td>
                    {label(source.approval_status)}
                    <div className="tiny muted">
                      Legal: {label(source.legal_review_status)}
                    </div>
                  </td>
                  <td>
                    {source.last_run ? label(source.last_run.status) : "Never"}
                    {source.last_run ? (
                      <div className="tiny muted">
                        {source.last_run.records_seen} seen ·{" "}
                        {source.last_run.scan_complete ? "complete" : "partial"}
                      </div>
                    ) : null}
                  </td>
                  <td>{dateLabel(source.next_due_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
