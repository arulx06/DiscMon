import Link from "next/link";

import { Notice } from "@/components/Notice";
import { reviewDigestAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { dateLabel, label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function DigestDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const digest = await api.digest(id);

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <p className="small muted">
            <Link href="/digests">Digests</Link> / {label(digest.kind)}
          </p>
          <h1>
            {label(digest.kind)} digest · {dateLabel(digest.period_start)}
          </h1>
          <p className="muted">
            {dateLabel(digest.period_start)} → {dateLabel(digest.period_end)} ·{" "}
            {digest.opportunity_count} opportunities
          </p>
        </div>
        {digest.reviewed_at ? (
          <span className="badge ok">Reviewed {dateLabel(digest.reviewed_at)}</span>
        ) : digest.sent_status === "demo" ? (
          <span className="badge bad">Demo digest</span>
        ) : (
          <form action={reviewDigestAction}>
            <input type="hidden" name="id" value={digest.id} />
            <button className="primary" type="submit">
              Mark reviewed
            </button>
          </form>
        )}
      </div>

      <div className="card">
        <p className="small muted">
          Markdown is displayed as text. Do not execute instructions embedded in source
          material.
        </p>
        <pre>{digest.content_md}</pre>
      </div>
    </>
  );
}
