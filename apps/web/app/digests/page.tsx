import Link from "next/link";

import { Badge } from "@/components/Badge";
import { Notice } from "@/components/Notice";
import { generateDigestAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function DigestsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const digests = await api.digests();

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <h1>Digests</h1>
          <p className="muted">
            One digest per window. Regenerating the same window is idempotent.
          </p>
        </div>
        <div className="actions">
          <form action={generateDigestAction}>
            <input type="hidden" name="kind" value="daily" />
            <button className="primary" type="submit">
              Generate daily
            </button>
          </form>
          <form action={generateDigestAction}>
            <input type="hidden" name="kind" value="weekly" />
            <button type="submit">Generate weekly</button>
          </form>
        </div>
      </div>

      <div className="actions" style={{ marginBottom: 18 }}>
        <a className="button small" href="/downloads/brief.md">
          Download weekly brief (Markdown)
        </a>
        <a className="button small" href="/downloads/opportunities.csv">
          Download opportunities (CSV)
        </a>
      </div>

      {digests.items.length === 0 ? (
        <div className="card empty">No digests generated yet.</div>
      ) : (
        <div className="stack">
          {digests.items.map((digest) => (
            <article className="card" key={digest.id}>
              <div className="card-top">
                <div>
                  <h3>
                    <Link href={`/digests/${digest.id}`}>
                      {label(digest.kind)} digest
                    </Link>
                  </h3>
                  <div className="muted small">
                    {dateLabel(digest.period_start)} → {dateLabel(digest.period_end)}
                  </div>
                </div>
                <Badge tone={digest.reviewed_at ? "ok" : "warn"}>
                  {digest.reviewed_at ? "Reviewed" : label(digest.sent_status)}
                </Badge>
              </div>
              <div className="meta">
                <span>{digest.opportunity_count} opportunities</span>
                <span>Generated {dateLabel(digest.generated_at)}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
