import Link from "next/link";

import { Badge } from "@/components/Badge";
import { api } from "@/lib/api";
import { label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function DeadlinesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const horizon = Number.parseInt(first(params.horizon_days) || "90", 10);
  const allowed = [30, 90, 180, 365].includes(horizon) ? horizon : 90;
  const deadlines = await api.deadlines(allowed);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Deadlines</h1>
          <p className="muted">
            {deadlines.total} dated action{deadlines.total === 1 ? "" : "s"} within{" "}
            {allowed} days. Date-only and month-only values never invent a cutoff time.
          </p>
        </div>
        <a className="button primary" href="/downloads/deadlines.ics">
          Download calendar
        </a>
      </div>

      <div className="filter-bar">
        <span className="small muted">Horizon</span>
        {[30, 90, 180, 365].map((days) => (
          <Link
            key={days}
            className={`button small ${days === allowed ? "primary" : ""}`}
            href={`/deadlines?horizon_days=${days}`}
          >
            {days} days
          </Link>
        ))}
      </div>

      {deadlines.items.length === 0 ? (
        <div className="card empty">No published deadlines in this horizon.</div>
      ) : (
        <div className="stack">
          {deadlines.items.map((item) => (
            <article className="card" key={item.id}>
              <div className="card-top">
                <div>
                  <h3>
                    <Link href={`/opportunities/${item.id}`}>{item.title}</Link>
                  </h3>
                  <div className="muted small">{item.organization ?? "Unknown organization"}</div>
                </div>
                <Badge
                  tone={
                    item.days_until_deadline !== null && item.days_until_deadline <= 7
                      ? "bad"
                      : "warn"
                  }
                >
                  {item.days_until_deadline === null
                    ? "No countdown"
                    : `${item.days_until_deadline} day${item.days_until_deadline === 1 ? "" : "s"}`}
                </Badge>
              </div>
              <div className="meta">
                <span>{item.deadline_label}</span>
                <span>{label(item.bucket)}</span>
                <span>{item.location || "Location not published"}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
