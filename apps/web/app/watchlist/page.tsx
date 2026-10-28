import Link from "next/link";

import { OpportunityCard } from "@/components/OpportunityCard";
import { api } from "@/lib/api";
import { label } from "@/lib/format";

export const dynamic = "force-dynamic";

const groups = ["watch", "prepare", "research"] as const;

export default async function WatchlistPage() {
  const results = await Promise.all(
    groups.map((decision) => api.opportunities({ decision, limit: 50 })),
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Watchlist</h1>
          <p className="muted">Records you marked to watch, prepare or research.</p>
        </div>
        <Link className="button" href="/opportunities?decision=unreviewed">
          Review unreviewed
        </Link>
      </div>

      {groups.map((decision, index) => {
        const listing = results[index];
        return (
          <section key={decision}>
            <h2>
              {label(decision)} <span className="muted small">({listing.total})</span>
            </h2>
            {listing.items.length === 0 ? (
              <div className="card empty">No records marked “{label(decision)}”.</div>
            ) : (
              <div className="grid">
                {listing.items.map((item) => (
                  <OpportunityCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </>
  );
}
