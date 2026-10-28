import Link from "next/link";

import { Badge, EligibilityBadge, IndiaBadge } from "@/components/Badge";
import { dateLabel, deadlineText, label } from "@/lib/format";
import type { OpportunityCard as OpportunityCardType } from "@/lib/types";

export function OpportunityCard({
  item,
  followupDue,
}: {
  item: OpportunityCardType;
  followupDue?: string | null;
}) {
  return (
    <article className="card">
      <div className="card-top">
        <div>
          <h3>
            <Link href={`/opportunities/${item.id}`}>{item.title}</Link>
          </h3>
          <div className="muted small">{item.organization ?? "Unknown organization"}</div>
        </div>
        <div className="score" aria-label={`Score ${item.score ?? "unscored"}`}>
          {item.score ?? "–"}
        </div>
      </div>

      <div className="pill-row">
        {item.is_fixture ? <Badge tone="bad">Demo fixture</Badge> : null}
        <Badge tone={item.bucket === "act_now" ? "ok" : item.bucket === "excluded" ? "bad" : "warn"}>
          {label(item.bucket)}
        </Badge>
        <Badge>{label(item.type)}</Badge>
        <Badge>{label(item.life_state)}</Badge>
        <EligibilityBadge value={item.professional_eligibility} />
        <IndiaBadge value={item.india_eligibility} />
      </div>

      <div className="meta">
        <span>{item.location || "Location not published"}</span>
        <span>{label(item.workplace_type)}</span>
        <span>Deadline: {deadlineText(item)}</span>
        {item.compensation ? <span>{item.compensation}</span> : null}
      </div>

      {item.next_action ? (
        <p className="small">
          <strong>Next action:</strong> {item.next_action}
        </p>
      ) : null}
      {followupDue ? (
        <p className="small muted">Follow-up: {dateLabel(followupDue)}</p>
      ) : null}

      {item.why ? <p className="why">{item.why}</p> : null}

      <div className="actions">
        <Link className="button small" href={`/opportunities/${item.id}`}>
          Open record
        </Link>
        <a
          className="button small"
          href={item.official_url}
          rel="noreferrer noopener"
          target="_blank"
        >
          Official source
        </a>
      </div>
    </article>
  );
}
