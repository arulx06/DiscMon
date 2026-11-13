import { Notice } from "@/components/Notice";
import { RuntimeScheduleSection } from "@/components/RuntimeScheduleSection";
import { loadRuntimeScheduleAction, updateProfileAction } from "@/lib/actions";
import { api } from "@/lib/api";
import { label } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const profile = await api.profile();
  const runtimeSchedule = await loadRuntimeScheduleAction();

  return (
    <>
      <Notice notice={first(query.notice)} error={first(query.error)} />
      <div className="page-head">
        <div>
          <h1>Preferences</h1>
          <p className="muted">
            Profile version {profile.profile_version} · scoring {profile.scoring_version}.
            Changes never override eligibility hard gates.
          </p>
        </div>
      </div>

      <form action={updateProfileAction} className="card stack">
        <div className="form-grid">
          <label>
            Employment stage
            <select name="employment_stage" defaultValue={profile.employment_stage}>
              <option value="prejoin">Pre-join</option>
              <option value="employed">Employed</option>
            </select>
          </label>
          <label>
            Home country (ISO-2)
            <input name="home_country" defaultValue={profile.home_country} maxLength={2} />
          </label>
          <label>
            Preferred countries (comma separated)
            <input
              name="preferred_countries"
              defaultValue={profile.preferred_countries.join(", ")}
            />
          </label>
          <label>
            Timezone
            <input name="timezone" defaultValue={profile.timezone} />
          </label>
          <label className="check">
            <input name="student_status" type="checkbox" defaultChecked={profile.student_status} />{" "}
            Currently a student
          </label>
          <label className="check">
            <input
              name="relocation_allowed"
              type="checkbox"
              defaultChecked={profile.relocation_allowed}
            />{" "}
            Open to relocation
          </label>
          <label>
            Desired YOE minimum
            <input
              name="desired_yoe_min"
              type="number"
              min={0}
              max={50}
              defaultValue={profile.desired_yoe_min ?? ""}
            />
          </label>
          <label>
            Desired YOE maximum
            <input
              name="desired_yoe_max"
              type="number"
              min={0}
              max={50}
              defaultValue={profile.desired_yoe_max ?? ""}
            />
          </label>
          <label>
            Quiet hours start (0–23)
            <input
              name="quiet_hours_start"
              type="number"
              min={0}
              max={23}
              defaultValue={profile.quiet_hours_start}
            />
          </label>
          <label>
            Quiet hours end (0–23)
            <input
              name="quiet_hours_end"
              type="number"
              min={0}
              max={23}
              defaultValue={profile.quiet_hours_end}
            />
          </label>
          <label>
            Max immediate alerts / week
            <input
              name="max_immediate_alerts_per_week"
              type="number"
              min={0}
              max={50}
              defaultValue={profile.max_immediate_alerts_per_week}
            />
          </label>
          <label>
            Alert channels (comma separated)
            <input name="alert_channels" defaultValue={profile.alert_channels.join(", ")} />
          </label>
          <label className="wide">
            Opportunity categories
            <textarea name="categories" rows={2} defaultValue={profile.categories.join(", ")} />
          </label>
          <label className="wide">
            Skills
            <textarea name="skills" rows={2} defaultValue={profile.skills.join(", ")} />
          </label>
          <label className="wide">
            Ignore terms
            <textarea
              name="ignore_terms"
              rows={2}
              defaultValue={profile.ignore_terms.join(", ")}
            />
          </label>
        </div>
        <div className="actions">
          <button className="primary" type="submit">
            Save preferences
          </button>
        </div>
      </form>

      <section className="card" style={{ marginTop: 18 }}>
        <h2>Current channel values</h2>
        <div className="pill-row">
          {profile.alert_channels.map((channel) => (
            <span className="badge" key={channel}>
              {label(channel)}
            </span>
          ))}
        </div>
        <p className="small muted">
          Optional AI and external mirrors are off by default and cannot override hard
          gates.
        </p>
      </section>

      <RuntimeScheduleSection initialResult={runtimeSchedule} />
    </>
  );
}
