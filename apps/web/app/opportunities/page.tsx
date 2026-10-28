import Link from "next/link";

import { OpportunityCard } from "@/components/OpportunityCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const search = first(params.search);
  const bucket = first(params.bucket);
  const lifeState = first(params.life_state);
  const decision = first(params.decision);
  const includeFixtures = first(params.include_fixtures) === "1";
  const limit = 24;
  const offset = Number.parseInt(first(params.offset) || "0", 10) || 0;

  const listing = await api.opportunities({
    search,
    bucket,
    life_state: lifeState,
    decision,
    include_fixtures: includeFixtures,
    limit,
    offset,
  });

  const previous = Math.max(0, offset - limit);
  const next = offset + limit;
  const suffix = (value: number) => {
    const query = new URLSearchParams();
    for (const [key, val] of Object.entries({ search, bucket, life_state: lifeState, decision })) {
      if (val) {
        query.set(key, val);
      }
    }
    if (includeFixtures) {
      query.set("include_fixtures", "1");
    }
    query.set("offset", String(value));
    return `/opportunities?${query.toString()}`;
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Opportunities</h1>
          <p className="muted">
            {listing.total} record{listing.total === 1 ? "" : "s"} match the current filters.
          </p>
        </div>
        <Link className="button" href="/deadlines">
          Deadline view
        </Link>
      </div>

      <form className="filter-bar" method="get">
        {includeFixtures ? <input type="hidden" name="include_fixtures" value="1" /> : null}
        <label>
          Search
          <input name="search" defaultValue={search} placeholder="Title, organization…" />
        </label>
        <label>
          Bucket
          <select name="bucket" defaultValue={bucket}>
            <option value="">Any</option>
            <option value="act_now">Act now</option>
            <option value="prepare_early">Prepare early</option>
            <option value="keep_on_radar">Keep on radar</option>
            <option value="needs_verification">Needs verification</option>
            <option value="archive">Archive</option>
            <option value="excluded">Excluded</option>
          </select>
        </label>
        <label>
          Life state
          <select name="life_state" defaultValue={lifeState}>
            <option value="">Any</option>
            <option value="open">Open</option>
            <option value="upcoming">Upcoming</option>
            <option value="expired_unverified">Expired unverified</option>
            <option value="closed">Closed</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <label>
          Decision
          <select name="decision" defaultValue={decision}>
            <option value="">Any</option>
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
        <button className="primary" type="submit">
          Apply filters
        </button>
        <Link className="button" href="/opportunities">
          Reset
        </Link>
        <Link
          className={`button small ${includeFixtures ? "primary" : ""}`}
          href={includeFixtures ? "/opportunities" : "/opportunities?include_fixtures=1"}
        >
          {includeFixtures ? "Hide demo fixtures" : "Show demo fixtures"}
        </Link>
      </form>

      {includeFixtures ? (
        <div className="notice">
          Demo fixtures are labelled test records. They are not real opportunities.
        </div>
      ) : null}

      {listing.items.length === 0 ? (
        <div className="card empty">
          No opportunities match these filters. Check sources and scans before assuming
          nothing exists.
        </div>
      ) : (
        <div className="grid">
          {listing.items.map((item) => (
            <OpportunityCard key={item.id} item={item} />
          ))}
        </div>
      )}

      <div className="pagination">
        {offset > 0 ? (
          <Link className="button small" href={suffix(previous)}>
            Previous
          </Link>
        ) : null}
        <span className="small muted">
          {offset + 1}–{Math.min(offset + limit, listing.total)} of {listing.total}
        </span>
        {next < listing.total ? (
          <Link className="button small" href={suffix(next)}>
            Next
          </Link>
        ) : null}
      </div>
    </>
  );
}
