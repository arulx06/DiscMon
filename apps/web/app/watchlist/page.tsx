import Link from "next/link";

import { OpportunityCard } from "@/components/OpportunityCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WatchlistPage() {
  const watchlist = await api.watchlist();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Watchlist</h1>
          <p className="muted">
            Preparation pipeline with editable next actions and follow-up dates.
            {watchlist.followups_due > 0
              ? ` ${watchlist.followups_due} follow-up${watchlist.followups_due === 1 ? "" : "s"} due now.`
              : " No follow-ups are due."}
          </p>
        </div>
        <Link className="button" href="/opportunities?decision=unreviewed">
          Review unreviewed
        </Link>
      </div>

      {watchlist.groups.map((group) => (
        <section key={group.key}>
          <h2>
            {group.title} <span className="muted small">({group.total})</span>
          </h2>
          {group.items.length === 0 ? (
            <div className="card empty">No records in this stage.</div>
          ) : (
            <div className="grid">
              {group.items.map((item) => (
                <OpportunityCard
                  key={item.id}
                  item={item}
                  followupDue={item.followup_due_at}
                />
              ))}
            </div>
          )}
        </section>
      ))}
    </>
  );
}
