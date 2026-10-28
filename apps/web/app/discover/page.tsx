import { Badge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import { decideDiscoveryAction, inspectUrlAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const candidates = await api.discovery();

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <h1>Discovery</h1>
          <p className="muted">
            Inspected URLs become candidates. Nothing is crawled until a source is
            approved and enabled.
          </p>
        </div>
      </div>

      <form action={inspectUrlAction} className="filter-bar">
        <label>
          URL to inspect
          <input name="url" type="url" required placeholder="https://…" />
        </label>
        <label>
          Notes
          <input name="notes" maxLength={2000} placeholder="Where this came from" />
        </label>
        <button className="primary" type="submit">
          Add candidate
        </button>
      </form>

      {candidates.items.length === 0 ? (
        <div className="card empty">No discovery candidates yet.</div>
      ) : (
        <div className="stack">
          {candidates.items.map((candidate) => (
            <article className="card" key={candidate.id}>
              <div className="card-top">
                <div>
                  <h3>
                    <a href={candidate.url} rel="noreferrer noopener" target="_blank">
                      {candidate.url}
                    </a>
                  </h3>
                  <div className="muted small">
                    Found {dateLabel(candidate.discovered_at)}
                    {candidate.candidate_type ? ` · ${label(candidate.candidate_type)}` : ""}
                  </div>
                </div>
                <Badge
                  tone={
                    candidate.approval_status === "approved"
                      ? "ok"
                      : candidate.approval_status === "rejected"
                        ? "bad"
                        : "warn"
                  }
                >
                  {label(candidate.approval_status)}
                </Badge>
              </div>
              <div className="meta">
                <span>Suggested adapter: {label(candidate.suggested_adapter)}</span>
                <span>Officialness guess: {label(candidate.officialness_guess)}</span>
                <span>Legal: {label(candidate.legal_review_status)}</span>
              </div>
              {candidate.notes ? <p className="small muted">{candidate.notes}</p> : null}
              {candidate.approval_status === "candidate" ? (
                <div className="actions">
                  <form action={decideDiscoveryAction}>
                    <input type="hidden" name="id" value={candidate.id} />
                    <input type="hidden" name="decision" value="approved" />
                    <button className="primary small" type="submit">
                      Approve
                    </button>
                  </form>
                  <form action={decideDiscoveryAction}>
                    <input type="hidden" name="id" value={candidate.id} />
                    <input type="hidden" name="decision" value="rejected" />
                    <button className="small" type="submit">
                      Reject
                    </button>
                  </form>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
