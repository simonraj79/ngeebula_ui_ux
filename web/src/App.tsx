import { useEffect, useMemo, useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Archive,
  ArrowRight,
  BookOpen,
  CalendarRange,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Database,
  FileArchive,
  Filter,
  GitCompareArrows,
  Info,
  LayoutDashboard,
  Menu,
  Network,
  PanelLeftClose,
  Play,
  RefreshCw,
  Route as RouteIcon,
  Search,
  Settings2,
  ShieldCheck,
  Table2,
  Upload,
  Wrench,
  X,
} from "lucide-react";
import {
  ApiError,
  DatasetSummary,
  PlanBundle,
  ScenarioId,
  ScheduleRow,
  ps1Api,
} from "./api";

const nav = [
  ["/", "Overview", LayoutDashboard],
  ["/plan", "Plan access", GitCompareArrows],
  ["/schedule", "Schedule", CalendarRange],
  ["/data", "Data & imports", Database],
  ["/requests", "Work requests", Wrench],
  ["/about", "About", BookOpen],
] as const;

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside
        className={menuOpen ? "sidebar open" : "sidebar"}
        aria-label="Primary navigation"
      >
        <div className="brand">
          <span className="brand-mark">
            <RouteIcon aria-hidden />
          </span>
          <div>
            <strong>Ngeebula</strong>
            <small>Access planning</small>
          </div>
        </div>
        <nav>
          {nav.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <Icon aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck aria-hidden />
          <span>
            Decision support
            <br />
            <small>Approval remains human</small>
          </span>
        </div>
      </aside>
      {menuOpen && (
        <button
          className="scrim"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <div className="workspace">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            aria-label="Open navigation"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? <X /> : <Menu />}
          </button>
          <div className="crumb">PS1 engineering access planner</div>
          <span className="environment">
            <span /> Planning workspace
          </span>
        </header>
        <main id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/plan" element={<Plan />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/data" element={<DataImports />} />
            <Route path="/requests" element={<WorkRequests />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function PageHeader({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action && <div className="page-action">{action}</div>}
    </header>
  );
}

function StatusMessage({
  loading,
  error,
  empty,
}: {
  loading?: boolean;
  error?: string;
  empty?: string;
}) {
  if (loading)
    return (
      <div className="notice">
        <RefreshCw className="spin" aria-hidden />
        <div>
          <strong>Loading planning data</strong>
          <p>Reading the current workspace snapshot.</p>
        </div>
      </div>
    );
  if (error)
    return (
      <div className="notice error" role="alert">
        <AlertTriangle aria-hidden />
        <div>
          <strong>Data unavailable</strong>
          <p>{error}</p>
        </div>
      </div>
    );
  if (empty)
    return (
      <div className="notice">
        <Info aria-hidden />
        <div>
          <strong>No dataset loaded</strong>
          <p>{empty}</p>
        </div>
      </div>
    );
  return null;
}

function useDataset() {
  const [data, setData] = useState<DatasetSummary | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    setError("");
    ps1Api
      .getDataset()
      .then(setData)
      .catch((e) =>
        setError(
          e instanceof ApiError ? e.message : "Could not read the dataset.",
        ),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  return { data, error, loading, reload: load };
}

function Overview() {
  const { data, error, loading, reload } = useDataset();
  return (
    <>
      <PageHeader
        eyebrow="Planning workspace"
        title="Engineering access overview"
        action={
          <button className="secondary" onClick={reload}>
            <RefreshCw aria-hidden />
            Refresh data
          </button>
        }
      >
        Understand the demand book before choosing a policy. Counts appear only
        when a validated dataset is loaded.
      </PageHeader>
      <StatusMessage
        loading={loading}
        error={error}
        empty={
          !data
            ? "Import the supplied eight CSV files or ZIP to begin."
            : undefined
        }
      />
      {data && (
        <>
          <section className="metric-grid" aria-label="Dataset metrics">
            <Metric label="Contracts" value={data.contracts} />
            <Metric label="Activities" value={data.activities} />
            <Metric label="Locations" value={data.locations} />
            <Metric label="Access weeks" value={data.access_weeks} />
          </section>
          <section className="two-column">
            <article className="panel">
              <PanelTitle
                icon={Network}
                title="Two-line network"
                subtitle="Exact PS1 Alpha and Beta identifiers"
              />
              <NetworkMap stations={data.network_stations} />
            </article>
            <article className="panel">
              <PanelTitle
                icon={Archive}
                title="Dataset provenance"
                subtitle="The active planning source"
              />
              <dl className="definition-list">
                <div>
                  <dt>Source</dt>
                  <dd>{data.source_name}</dd>
                </div>
                {data.source_commit && (
                  <div>
                    <dt>Snapshot</dt>
                    <dd className="mono">{data.source_commit.slice(0, 12)}</dd>
                  </div>
                )}
                <div>
                  <dt>Horizon</dt>
                  <dd>
                    {data.horizon_start} to {data.horizon_end}
                  </dd>
                </div>
                {data.imported_at !== "Not reported" && (
                  <div>
                    <dt>Imported</dt>
                    <dd>{formatTime(data.imported_at)}</dd>
                  </div>
                )}
                <div>
                  <dt>Dataset ID</dt>
                  <dd className="mono">{data.dataset_id}</dd>
                </div>
              </dl>
              {data.warnings?.length > 0 && (
                <details className="assumptions">
                  <summary>
                    Source assumptions and validator status{" "}
                    <ChevronDown aria-hidden />
                  </summary>
                  <ul>
                    {data.warnings.map((warning, index) => (
                      <li key={index}>
                        <Info aria-hidden />
                        {warning}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          </section>
        </>
      )}
      <section className="panel rules">
        <PanelTitle
          icon={ShieldCheck}
          title="Non-negotiable rules"
          subtitle="Every generated schedule must pass all rigid checks"
        />
        <div className="rule-grid">
          <Rule n="01" title="Schedule every activity">
            Workload is conserved; partial plans are not feasible.
          </Rule>
          <Rule n="02" title="Respect closures">
            Sector, buffer and cross-line tunnel rules stay intact.
          </Rule>
          <Rule n="03" title="Use legal possessions">
            Location mixes, weekly allocation and workfronts are enforced.
          </Rule>
        </div>
      </section>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function PanelTitle({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: typeof Network;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="panel-title">
      <span>
        <Icon aria-hidden />
      </span>
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}
function Rule({
  n,
  title,
  children,
}: {
  n: string;
  title: string;
  children: string;
}) {
  return (
    <div className="rule">
      <span>{n}</span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

function NetworkMap({
  stations,
}: {
  stations: DatasetSummary["network_stations"];
}) {
  const rows = (["ALP", "BET"] as const).map((code) =>
    stations
      .filter((station) => station.line_code === code)
      .sort((a, b) => a.seq - b.seq),
  );
  return (
    <div
      className="network-map"
      role="img"
      aria-label="Alpha ALP and Beta BET lines meet through the H01 H02 interchange tunnel sector."
    >
      {rows.map((row, index) => (
        <div
          className={`network-row ${index === 0 ? "alpha" : "beta"}`}
          key={index}
        >
          <b>{index === 0 ? "Alpha · ALP" : "Beta · BET"}</b>
          <div>
            {row.map((station) => (
              <span
                className={station.is_interchange ? "hub" : ""}
                key={`${station.line_code}-${station.station_id}`}
              >
                {station.station_id}
              </span>
            ))}
          </div>
        </div>
      ))}
      <small className="network-note">
        <GitCompareArrows aria-hidden /> H01–H02 interchange tunnel is
        represented independently on each line.
      </small>
    </div>
  );
}

const scenarios: Array<{
  id: ScenarioId;
  name: string;
  strap: string;
  body: string;
  rigid: string;
  flexible: string;
}> = [
  {
    id: "A",
    name: "Strict supply",
    strap: "Flexible schedule",
    body: "Stay inside granted access and forbid ECLO. Absorb unavoidable delay by priority.",
    rigid: "Supply and ECLO",
    flexible: "Completion dates",
  },
  {
    id: "B",
    name: "Strict schedule",
    strap: "Flexible supply",
    body: "Hold planned completion dates. Score additional access nights and ECLO used to get there.",
    rigid: "Completion dates",
    flexible: "Supply and ECLO",
  },
  {
    id: "C",
    name: "Balanced trade-off",
    strap: "Controlled elasticity",
    body: "Trade limited localized capacity strain against priority-weighted delay.",
    rigid: "All safety rules",
    flexible: "Supply and dates",
  },
];

function Plan() {
  const { data, error, loading } = useDataset();
  const [selected, setSelected] = useState<ScenarioId>("C");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PlanBundle | null>(null);
  const [runError, setRunError] = useState("");
  const [location, setLocation] = useState("");
  const [week, setWeek] = useState("");
  const [capacity, setCapacity] = useState(1);
  const [baseline, setBaseline] = useState<PlanBundle | null>(null);
  useEffect(() => {
    ps1Api.getPlan(selected).then(setBaseline).catch(() => setBaseline(null));
  }, [selected]);
  useEffect(() => {
    if (!data) return;
    setLocation((current) => current || data.location_options[0]?.id || "");
    setWeek((current) => current || data.week_options[0]?.value || "");
  }, [data]);
  const generate = async (whatIf = false) => {
    setRunning(true);
    setRunError("");
    setResult(null);
    try {
      const next = await ps1Api.generatePlan(selected, {
          baseline_run_id: baseline?.run_id,
          ...(whatIf ? {
                disruptions: [
                  { location_id: location.trim(), week: week.trim(), capacity },
                ],
              } : {}),
        });
      setResult(next);
      setBaseline(next);
    } catch (e) {
      setRunError(
        e instanceof ApiError
          ? e.message
          : "The planner did not return a result.",
      );
    } finally {
      setRunning(false);
    }
  };
  return (
    <>
      <PageHeader eyebrow="Step 1 of 2" title="Choose a planning policy">
        Each scenario changes which lever may flex. Safety, workload and
        possession rules never do.
      </PageHeader>
      <StatusMessage
        loading={loading}
        error={error}
        empty={
          !data
            ? "Load and validate a dataset before generating a plan."
            : undefined
        }
      />
      <fieldset className="scenario-grid" disabled={!data || running}>
        <legend className="sr-only">Planning scenario</legend>
        {scenarios.map((s) => (
          <label
            className={selected === s.id ? "scenario selected" : "scenario"}
            key={s.id}
          >
            <input
              type="radio"
              name="scenario"
              value={s.id}
              checked={selected === s.id}
              onChange={() => setSelected(s.id)}
            />
            <span className="scenario-letter">{s.id}</span>
            <span className="scenario-title">
              <strong>{s.name}</strong>
              <small>{s.strap}</small>
            </span>
            <p>{s.body}</p>
            <span className="policy-row">
              <b>Rigid</b>
              {s.rigid}
            </span>
            <span className="policy-row">
              <b>May flex</b>
              {s.flexible}
            </span>
            {selected === s.id && (
              <span className="select-mark">
                <CheckCircle2 aria-hidden />
                Selected
              </span>
            )}
          </label>
        ))}
      </fieldset>
      <details className="panel what-if">
        <summary>
          <Settings2 aria-hidden />
          <span>
            <strong>What-if: temporary capacity cut</strong>
            <small>Optional re-plan for one location and week</small>
          </span>
          <ChevronDown aria-hidden />
        </summary>
        <div className="what-if-fields">
          <label>
            Location
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            >
              {data?.location_options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.id} · {option.line} · {option.bound || "both bounds"} · nominal {option.capacity}
                </option>
              ))}
            </select>
          </label>
          <label>
            Week
            <select
              value={week}
              onChange={(e) => setWeek(e.target.value)}
            >
              {data?.week_options.map((option) => (
                <option key={option.value} value={option.value}>
                  Week {option.value} · {option.start}–{option.end}
                </option>
              ))}
            </select>
          </label>
          <label>
            New capacity
            <input
              type="number"
              min="0"
              value={capacity}
              onChange={(e) => setCapacity(Math.max(0, Number(e.target.value)))}
            />
          </label>
          <button
            className="secondary"
            disabled={!data || running || !location.trim() || !week.trim()}
            onClick={() => generate(true)}
          >
            Assess impact
          </button>
        </div>
        <p className="fine-print">
          {baseline?.run_id
            ? `Compared with the last completed Scenario ${selected} plan from ${formatTime(baseline.generated_at)} (${baseline.run_id.slice(0, 8)}).`
            : `No completed Scenario ${selected} plan is stored in this browser yet; the first run establishes the baseline.`}
        </p>
      </details>
      <div className="action-bar">
        <div>
          <strong>Scenario {selected}</strong>
          <span>
            {scenarios.find((s) => s.id === selected)?.name} · review is
            required before export
          </span>
        </div>
        <button
          className="primary"
          onClick={() => generate(false)}
          disabled={!data || running}
        >
          {running ? (
            <>
              <RefreshCw className="spin" aria-hidden />
              Generating…
            </>
          ) : (
            <>
              <Play aria-hidden />
              Generate plan
            </>
          )}
        </button>
      </div>
      {runError && <StatusMessage error={runError} />}{" "}
      {result && <ResultSummary bundle={result} />}
    </>
  );
}

function ResultSummary({ bundle }: { bundle: PlanBundle }) {
  const r = bundle.result;
  const horizonExplanation = bundle.explanations.find((item) =>
    item.code.includes("extending_flat_nominal"),
  );
  return (
    <section
      className={r.feasible ? "panel result feasible" : "panel result failed"}
      aria-live="polite"
    >
      <PanelTitle
        icon={r.feasible ? CheckCircle2 : AlertTriangle}
        title={
          r.feasible ? "Locally checked complete plan" : "Plan needs attention"
        }
        subtitle={`Scenario ${r.scenario} · generated ${formatTime(bundle.generated_at)}`}
      />
      {horizonExplanation && (
        <div className="notice horizon-note">
          <CalendarRange aria-hidden />
          <div>
            <strong>Schedule extends beyond target dates</strong>
            <p>{horizonExplanation.message}</p>
          </div>
        </div>
      )}
      {bundle.changes?.baseline_run_id && (
        <details className="comparison-detail">
          <summary>
            {bundle.changes.count} activities changed from the prior plan
          </summary>
          {bundle.changes.note && <p>{bundle.changes.note}</p>}
          {bundle.changes.moved_activities.slice(0, 12).map((change) => (
            <div className="comparison-row" key={change.activity_id}>
              <strong>{change.activity_id}</strong>
              <span>Before: {formatPositions(change.before)}</span>
              <span>After: {formatPositions(change.after)}</span>
            </div>
          ))}
          {bundle.changes.count > 12 && (
            <p>Showing 12 of {bundle.changes.count} changed activities.</p>
          )}
        </details>
      )}
      <div className="metric-grid compact">
        <Metric label="Hard violations" value={r.hard_violations.length} />
        <Metric label="Nights scheduled" value={r.detail.nights_scheduled} />
        <Metric label="ECLO nights" value={r.soft_scores.eclo_nights_total} />
        <Metric label="Overrun days" value={r.soft_scores.overrun_days_total} />
        <Metric label="Excess access nights" value={r.soft_scores.excess_access_nights_total} />
        <Metric label="Objective score" value={r.soft_scores.objective_score ?? "Not reported"} />
      </div>
      <p className="fine-print">A lower objective score is better only when comparing complete plans within Scenario {r.scenario}.</p>
      {r.hard_violations.length > 0 && (
        <WarningList items={r.hard_violations.map((v) => v.detail)} />
      )}
      <div className="result-actions">
        <NavLink className="button-link" to={`/schedule?scenario=${r.scenario}`}>
          Review schedule <ArrowRight aria-hidden />
        </NavLink>
        <button
          className="secondary"
          disabled={!bundle.run_id || !r.complete}
          onClick={() =>
            bundle.run_id && ps1Api.downloadValidation(bundle.run_id)
          }
        >
          <Archive aria-hidden />
          Download local validation JSON
        </button>
      </div>
      <p className="fine-print">
        Local validation implements the published rules. The official
        trackaccess validator is not bundled, so this is not official
        certification.
      </p>
    </section>
  );
}

function Schedule() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryScenario = searchParams.get("scenario");
  const initialScenario: ScenarioId = queryScenario === "A" || queryScenario === "B" ? queryScenario : "C";
  const [scenario, setScenario] = useState<ScenarioId>(initialScenario),
    [bundle, setBundle] = useState<PlanBundle | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [view, setView] = useState<"timeline" | "table">("timeline"),
    [line, setLine] = useState("All"),
    [type, setType] = useState("All"),
    [query, setQuery] = useState(""),
    [downloadError, setDownloadError] = useState("");
  useEffect(() => {
    setLoading(true);
    setError("");
    ps1Api
      .getPlan(scenario)
      .then(setBundle)
      .catch((e) => {
        setBundle(null);
        setError(
          e instanceof ApiError ? e.message : "Could not read the schedule.",
        );
      })
      .finally(() => setLoading(false));
  }, [scenario]);
  const rows = useMemo(
    () =>
      bundle?.schedule.filter(
        (r) =>
          (line === "All" || r.line === line) &&
          (type === "All" || r.access_type === type) &&
          `${r.activity_id} ${r.contract_number}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ) ?? [],
    [bundle, line, type, query],
  );
  const download = async () => {
    if (!bundle?.run_id || !bundle.result.feasible) return;
    setDownloadError("");
    try {
      await ps1Api.downloadRun(bundle.run_id);
    } catch (e) {
      setDownloadError(e instanceof ApiError ? e.message : "Download failed.");
    }
  };
  return (
    <>
      <PageHeader
        eyebrow="Step 2 of 2"
        title="Review the schedule"
        action={
          <button
            className="primary"
            disabled={!bundle?.run_id || !bundle.result.feasible}
            onClick={download}
          >
            <Archive aria-hidden />
            Download submission
          </button>
        }
      >
        Inspect every placement visually or in the exact-value table before
        exporting.
      </PageHeader>
      <div className="toolbar">
        <label>
          Scenario
          <select
            aria-label="Scenario"
            value={scenario}
            onChange={(e) => {
              const value = e.target.value as ScenarioId;
              setScenario(value);
              setSearchParams({ scenario: value });
            }}
          >
            <option>A</option>
            <option>B</option>
            <option>C</option>
          </select>
        </label>
        <span className="toolbar-separator" />
        <label>
          <Search aria-hidden />
          Search
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Activity or contract"
          />
        </label>
        <label>
          <Filter aria-hidden />
          Line
          <select value={line} onChange={(e) => setLine(e.target.value)}>
            <option>All</option>
            <option>Alpha</option>
            <option>Beta</option>
          </select>
        </label>
        <label>
          Access type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option>All</option>
            {[...new Set(bundle?.schedule.map((row) => row.access_type).filter(Boolean) ?? [])].sort().map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <div className="segmented" aria-label="Schedule view">
          <button
            aria-pressed={view === "timeline"}
            onClick={() => setView("timeline")}
          >
            <Activity aria-hidden />
            Timeline
          </button>
          <button
            aria-pressed={view === "table"}
            onClick={() => setView("table")}
          >
            <Table2 aria-hidden />
            Exact table
          </button>
        </div>
      </div>
      {downloadError && <StatusMessage error={downloadError} />}
      <StatusMessage
        loading={loading}
        error={error}
        empty={
          !bundle ? "Generate this scenario before reviewing it." : undefined
        }
      />
      {bundle &&
        (view === "timeline" ? (
          <Timeline rows={rows} />
        ) : (
          <ScheduleTable rows={rows} />
        ))}
    </>
  );
}

function Timeline({ rows }: { rows: ScheduleRow[] }) {
  const maxWeek = Math.max(0, ...rows.map((row) => Number(row.week) || 0));
  const weeks = Array.from({ length: maxWeek }, (_, index) => String(index + 1));
  const grouped = [...rows.reduce((map, row) => {
    const current = map.get(row.activity_id) ?? [];
    current.push(row);
    map.set(row.activity_id, current);
    return map;
  }, new Map<string, ScheduleRow[]>()).entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
  return (
    <section className="panel schedule-panel">
      <div className="schedule-heading">
        <div>
          <h2>Weekly access plan</h2>
          <p>
            {grouped.length} activities · {rows.length} access placements
          </p>
          <small className="scroll-hint">{weeks.length} weeks — scroll horizontally to review the full horizon</small>
        </div>
        <span className="legend">
          <i className="alpha-dot" />
          Alpha <i className="beta-dot" />
          Beta <i className="eclo-dot" />
          ECLO
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="empty-copy">No placements match these filters.</p>
      ) : (
        <div
          className="gantt"
          tabIndex={0}
          role="region"
          aria-label={`Weekly access timeline across ${weeks.length} weeks. Scroll horizontally; the exact table is available above.`}
          style={
            { "--weeks": Math.max(weeks.length, 1) } as React.CSSProperties
          }
        >
          <div className="gantt-head">
            <span>Activity</span>
            {weeks.map((w) => (
              <b key={w}>{w}</b>
            ))}
          </div>
          {grouped.map(([activityId, placements]) => {
            const r = placements[0];
            return <div className="gantt-row" key={activityId}>
              <span>
                <strong>{activityId}</strong>
                <small>
                  {r.contract_number} · {r.start_location_id}–
                  {r.end_location_id}
                </small>
              </span>
              {weeks.map((w) => (
                <i
                  key={w}
                  className={
                    placements.some((placement) => placement.week === w)
                      ? `bar ${r.line.toLowerCase()} ${r.eclo ? "eclo" : ""}`
                      : ""
                  }
                  title={
                    placements.some((placement) => placement.week === w)
                      ? `${activityId}, ${placements.filter((placement) => placement.week === w).length} access night(s)`
                      : undefined
                  }
                >
                  {placements.some((placement) => placement.week === w) ? (
                    <em>{placements.filter((placement) => placement.week === w).length}</em>
                  ) : null}
                </i>
              ))}
            </div>;
          })}
        </div>
      )}
    </section>
  );
}

function ScheduleTable({ rows }: { rows: ScheduleRow[] }) {
  return (
    <section className="panel table-panel">
      <div className="schedule-heading">
        <div>
          <h2>Exact schedule values</h2>
          <p>Keyboard-scrollable alternative to the timeline.</p>
        </div>
      </div>
      <div className="table-scroll" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th>Activity</th>
              <th>Contract</th>
              <th>Line</th>
              <th>Access type</th>
              <th>Week</th>
              <th>Section</th>
              <th>Night</th>
              <th>ECLO</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.activity_id}-${i}`}>
                <td>{r.activity_id}</td>
                <td>{r.contract_number}</td>
                <td>
                  <span className={`line-tag ${r.line.toLowerCase()}`}>
                    {r.line}
                  </span>
                </td>
                <td>{r.access_type}</td>
                <td>{r.week}</td>
                <td>
                  {r.start_location_id} → {r.end_location_id}
                </td>
                <td>{r.access_night}</td>
                <td>{r.eclo ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DataImports() {
  const { data, error, loading, reload } = useDataset();
  const [files, setFiles] = useState<File[]>([]),
    [importing, setImporting] = useState(false),
    [feedback, setFeedback] = useState("");
  const select = (selected?: FileList | File[]) => {
    setFeedback("");
    const next = Array.from(selected ?? []);
    if (!next.length) return;
    const valid = next.every((f) => f.name.toLowerCase().endsWith(".csv") || f.name.toLowerCase().endsWith(".zip"));
    if (!valid) {
      setFiles([]);
      setFeedback(
        "Choose a CSV or ZIP containing the supplied instance files.",
      );
      return;
    }
    setFiles(next);
  };
  const submit = async () => {
    if (!files.length) return;
    setImporting(true);
    setFeedback("");
    try {
      await ps1Api.importDataset(files);
      setFeedback(
        "Dataset imported and validated. Review its provenance below.",
      );
      setFiles([]);
      reload();
    } catch (e) {
      setFeedback(
        e instanceof ApiError
          ? e.message
          : "Import failed. Check the files and try again.",
      );
    } finally {
      setImporting(false);
    }
  };
  return (
    <>
      <PageHeader eyebrow="Controlled input" title="Data and imports">
        Load a supplied or hidden instance without changing its identifiers. The
        server validates structure before activation.
      </PageHeader>
      <section className="two-column import-grid">
        <article className="panel">
          <PanelTitle
            icon={Upload}
            title="Import planning instance"
            subtitle="Eight CSV files, individually or as a ZIP"
          />
          <label
            className="drop-zone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              select(e.dataTransfer.files);
            }}
          >
            <FileArchive aria-hidden />
            <strong>{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Choose eight CSV files or one ZIP"}</strong>
            <span>
              {files.length
                ? `${files.map((file) => file.name).join(", ")} · ${formatBytes(files.reduce((sum, file) => sum + file.size, 0))}`
                : "Drag and drop, or browse this device"}
            </span>
            <input
              type="file"
              multiple
              accept=".csv,.zip,text/csv,application/zip"
              onChange={(e) => select(e.target.files ?? undefined)}
            />
          </label>
          {feedback && (
            <p
              className={
                feedback.startsWith("Dataset imported")
                  ? "form-feedback success"
                  : "form-feedback"
              }
              role="status"
            >
              {feedback}
            </p>
          )}
          <button
            className="primary full"
            disabled={!files.length || importing}
            onClick={submit}
          >
            {importing ? (
              <>
                <RefreshCw className="spin" />
                Validating…
              </>
            ) : (
              <>
                <Upload />
                Import and validate
              </>
            )}
          </button>
          <button className="secondary full" onClick={() => { ps1Api.useSuppliedDataset(); setFeedback("Supplied dataset restored."); reload(); }}>
            Use supplied dataset
          </button>
          <p className="fine-print">
            Importing replaces the active PS1 planning dataset only after server
            validation. It does not create maintenance work requests.
          </p>
        </article>
        <article className="panel">
          <PanelTitle
            icon={Database}
            title="Active dataset"
            subtitle="Source and validation evidence"
          />
          <StatusMessage
            loading={loading}
            error={error}
            empty={!data ? "No validated dataset is active." : undefined}
          />
          {data && (
            <dl className="definition-list">
              <div>
                <dt>Source file</dt>
                <dd>{data.source_name}</dd>
              </div>
              <div>
                <dt>Dataset ID</dt>
                <dd className="mono">{data.dataset_id}</dd>
              </div>
              {data.imported_at !== "Not reported" && (
                <div>
                  <dt>Imported</dt>
                  <dd>{formatTime(data.imported_at)}</dd>
                </div>
              )}
              <div>
                <dt>Scope</dt>
                <dd>
                  {data.contracts} contracts · {data.activities} activities
                </dd>
              </div>
            </dl>
          )}
        </article>
      </section>
      <section className="panel">
        <PanelTitle
          icon={ShieldCheck}
          title="Provenance checklist"
          subtitle="What remains attached to every plan"
        />
        <div className="check-list">
          <span>
            <CheckCircle2 />
            Original Alpha/Beta identifiers
          </span>
          <span>
            <CheckCircle2 />
            Import timestamp and source name
          </span>
          <span>
            <CheckCircle2 />
            Scenario-specific validator result
          </span>
          <span>
            <CheckCircle2 />
            Exact submission values
          </span>
        </div>
      </section>
    </>
  );
}

function WorkRequests() {
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]),
    [catalog, setCatalog] = useState<Record<string, unknown>>({}),
    [audit, setAudit] = useState<Array<Record<string, unknown>>>([]),
    [error, setError] = useState(""),
    [feedback, setFeedback] = useState(""),
    [loading, setLoading] = useState(true),
    [selectedId, setSelectedId] = useState(0),
    [assetIndex, setAssetIndex] = useState(0),
    [stationIndex, setStationIndex] = useState(0),
    [manualLine, setManualLine] = useState(""),
    [manualTrack, setManualTrack] = useState(""),
    [description, setDescription] = useState(""),
    [deadline, setDeadline] = useState(""),
    [decisionNote, setDecisionNote] = useState(""),
    [executionReason, setExecutionReason] = useState(""),
    [executionStatus, setExecutionStatus] = useState("In progress");
  const assets = [
    ["Train doors", "rolling_stock", "Train door repair"],
    ["Wheels & brakes", "rolling_stock", "Brake pad replacement"],
    ["Rails", "track_and_permanent_way", "Rail replacement"],
    ["Points", "track_and_permanent_way", "Switch/point replacement"],
    ["Signals", "signalling_and_train_control", "Signal replacement"],
    [
      "Power",
      "power_and_electrical_systems",
      "Traction power fault troubleshooting",
    ],
    ["Drainage & pumps", "station_equipment", "Drainage pump repair"],
    [
      "Platform doors",
      "platform_screen_doors",
      "Door obstruction sensor repair",
    ],
  ] as const;
  const stations = (
    Array.isArray(catalog.stations) ? catalog.stations : []
  ) as Array<Record<string, unknown>>;
  const lines = (Array.isArray(catalog.lines) ? catalog.lines : []) as string[];
  const selected =
    jobs.find((job) => Number(job.job_id) === selectedId) ?? jobs[0];
  useEffect(() => {
    const status = String(selected?.status ?? "Not started");
    setExecutionStatus(status === "In progress" ? "Done" : status === "Not started" ? "In progress" : status);
  }, [selected?.job_id, selected?.status]);
  const reload = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextJobs, nextCatalog, nextAudit] = await Promise.all([
        ps1Api.getJobs(),
        ps1Api.getCatalog(),
        ps1Api.getAudit(),
      ]);
      setJobs(nextJobs);
      setCatalog(nextCatalog);
      setAudit(nextAudit);
      if (!selectedId && nextJobs[0]) setSelectedId(Number(nextJobs[0].job_id));
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not load work requests.",
      );
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void reload();
  }, []);
  const perform = async (action: () => Promise<unknown>, success: string) => {
    setFeedback("");
    setError("");
    try {
      await action();
      setFeedback(success);
      await reload();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "The action could not be completed.",
      );
    }
  };
  const create = () => {
    const station = stations[stationIndex];
    const asset = assets[assetIndex];
    const manualSite = assetIndex < 2;
    if (
      (!manualSite && !station) ||
      (manualSite && (!manualLine || !manualTrack.trim())) ||
      !deadline ||
      !description.trim()
    ) {
      setError(
        "Complete the asset, work location, description, and future deadline.",
      );
      return;
    }
    const localDeadline = `${deadline}:00+08:00`;
    const place = manualSite ? manualTrack.trim() : String(station.name);
    void perform(
      () =>
        ps1Api.createJob({
          name: `${asset[2]} — ${place}`,
          description,
          line: manualSite ? manualLine : station.line,
          track: manualSite
            ? manualTrack.trim()
            : `${String(station.code)} ${String(station.name)}`,
          ...(manualSite ? {} : { station_code: station.code }),
          deadline: localDeadline,
          catalog_category: asset[1],
          catalog_activity: asset[2],
          created_by: "Planner",
        }),
      "Request created. Review assessed requirements before planning.",
    );
  };
  return (
    <>
      <PageHeader eyebrow="Secondary workflow" title="Corrective work requests">
        Existing request, approval and execution records remain available
        separately from PS1 access planning.
      </PageHeader>
      <div className="notice">
        <Info />
        <div>
          <strong>Separate planning scopes</strong>
          <p>
            These records are not inferred from Alpha/Beta contracts and are not
            inserted into a PS1 schedule automatically.
          </p>
        </div>
      </div>
      <StatusMessage loading={loading} error={error} />
      {feedback && (
        <p className="form-feedback success" role="status">
          {feedback}
        </p>
      )}
      {!loading && !error && (
        <>
          <section className="panel request-create">
            <PanelTitle
              icon={Wrench}
              title="Add planned corrective work"
              subtitle="Catalog repair, then station-first location"
            />
            <fieldset className="asset-grid">
              <legend>Choose the asset</legend>
              {assets.map((asset, index) => (
                <label
                  className={
                    assetIndex === index
                      ? "asset-choice selected"
                      : "asset-choice"
                  }
                  key={asset[0]}
                >
                  <input
                    type="radio"
                    name="asset"
                    checked={assetIndex === index}
                    onChange={() => setAssetIndex(index)}
                  />
                  <strong>
                    {index + 1} · {asset[0]}
                  </strong>
                  <small>{asset[2]}</small>
                </label>
              ))}
            </fieldset>
            <div className="request-form">
              {assetIndex < 2 ? (
                <>
                  <label>
                    Relevant rail line
                    <select
                      value={manualLine}
                      onChange={(e) => setManualLine(e.target.value)}
                    >
                      <option value="">Choose a line</option>
                      {lines.map((line) => (
                        <option key={line}>{line}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Train, depot or worksite
                    <input
                      value={manualTrack}
                      onChange={(e) => setManualTrack(e.target.value)}
                      placeholder="Train 512, car 3; or depot road 4"
                    />
                  </label>
                </>
              ) : (
                <label>
                  Station and serving line
                  <select
                    value={stationIndex}
                    onChange={(e) => setStationIndex(Number(e.target.value))}
                  >
                    {stations.map((station, index) => (
                      <option
                        key={`${station.code}-${station.line}`}
                        value={index}
                      >
                        {String(station.name)} · {String(station.code)} ·{" "}
                        {String(station.line)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Completion deadline (SGT)
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </label>
              <label className="wide">
                Observed work
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the affected equipment and planned repair scope."
                />
              </label>
              <button className="primary" onClick={create}>
                Create request
              </button>
            </div>
          </section>
          <section className="panel">
            <div className="schedule-heading">
              <div>
                <h2>Current requests</h2>
                <p>{jobs.length} records from the existing maintenance API</p>
              </div>
            </div>
            {jobs.length === 0 ? (
              <p className="empty-copy">No work requests are available.</p>
            ) : (
              <div className="request-list">
                {jobs.slice(0, 50).map((j, i) => (
                  <article key={String(j.job_id ?? i)}>
                    <span className="priority-mark" />
                    <div>
                      <strong>{String(j.name ?? "Untitled request")}</strong>
                      <p>
                        {String(j.line ?? "Unverified line")} ·{" "}
                        {String(j.track ?? "Location not provided")}
                      </p>
                    </div>
                    <span className="status-pill">
                      {String(j.status ?? "Unknown")}
                    </span>
                    <ArrowRight aria-hidden />
                  </article>
                ))}
              </div>
            )}
            {jobs.length > 0 && (
              <div className="work-controls">
                <label>
                  Request to review
                  <select
                    value={Number(selected?.job_id ?? 0)}
                    onChange={(e) => setSelectedId(Number(e.target.value))}
                  >
                    {jobs.map((job) => (
                      <option
                        key={String(job.job_id)}
                        value={Number(job.job_id)}
                      >
                        #{String(job.job_id)} · {String(job.name)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary"
                  onClick={() =>
                    perform(
                      () => ps1Api.proposeMaintenance(),
                      "Schedule proposal generated. Human approval is still required.",
                    )
                  }
                >
                  <Play aria-hidden />
                  Generate schedule proposal
                </button>
              </div>
            )}
            {selected && (
              <article className="job-detail">
                <h3>{String(selected.name)}</h3>
                <p>{String(selected.description ?? "")}</p>
                <div className="job-facts">
                  <span>
                    <b>Location</b>
                    {String(selected.line)} · {String(selected.track)}
                  </span>
                  <span>
                    <b>Priority</b>
                    {String(selected.priority)}
                  </span>
                  <span>
                    <b>Duration</b>
                    {String(selected.duration_mins)} min
                  </span>
                  <span>
                    <b>Approval</b>
                    {selected.is_approved ? "Approved" : "Pending"}
                  </span>
                  <span>
                    <b>Required skills</b>
                    {Array.isArray(selected.required_skills)
                      ? selected.required_skills.join(", ")
                      : "Not assessed"}
                  </span>
                  <span>
                    <b>Crew</b>
                    {Array.isArray(selected.assigned_engineers)
                      ? selected.assigned_engineers.length
                      : 0}{" "}
                    / {String(selected.engineers_needed ?? 0)}
                  </span>
                  <span>
                    <b>Scheduled start</b>
                    {selected.scheduled_start ? formatTime(String(selected.scheduled_start)) : "Not scheduled"}
                  </span>
                  <span>
                    <b>Scheduled end</b>
                    {selected.scheduled_end ? formatTime(String(selected.scheduled_end)) : "Not scheduled"}
                  </span>
                </div>
                <div className="decision-grid">
                  <div>
                    <h4>Approval decision</h4>
                    <label>
                      Decision note
                      <textarea
                        value={decisionNote}
                        onChange={(e) => setDecisionNote(e.target.value)}
                        placeholder="Evidence reviewed or conditions"
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={!selected.scheduled_start || Boolean(selected.is_approved)}
                      onClick={() =>
                        perform(
                          () =>
                            ps1Api.approveJob(Number(selected.job_id), {
                              approved: true,
                              approved_by: "Planner",
                              reason: decisionNote || null,
                            }),
                          "Approval recorded.",
                        )
                      }
                    >
                      Approve for execution
                    </button>
                  </div>
                  <div>
                    <h4>Execution update</h4>
                    <label>
                      Next status
                      <select value={executionStatus} onChange={(e) => setExecutionStatus(e.target.value)}>
                        {String(selected.status) === "Not started" && <option value="In progress">Start work</option>}
                        {String(selected.status) === "In progress" && <><option value="Done">Complete</option><option value="Delay">Blocked / delayed</option></>}
                        {!["Not started", "In progress"].includes(String(selected.status)) && <option value={String(selected.status)}>{String(selected.status)} — no next action</option>}
                      </select>
                    </label>
                    <label>
                      Field update reason
                      <textarea
                        value={executionReason}
                        onChange={(e) => setExecutionReason(e.target.value)}
                        placeholder="Observed progress, handover or completion evidence"
                      />
                    </label>
                    <button
                      className="secondary"
                      disabled={
                        !selected.is_approved || !executionReason.trim() || !["Not started", "In progress"].includes(String(selected.status))
                      }
                      onClick={() =>
                        perform(
                          () =>
                            ps1Api.updateJobStatus(Number(selected.job_id), {
                              status: executionStatus,
                              updated_by: "Planner",
                              reason: executionReason,
                            }),
                          "Execution status updated.",
                        )
                      }
                    >
                      Record {executionStatus === "Done" ? "completion" : executionStatus === "Delay" ? "blocked status" : "start"}
                    </button>
                  </div>
                </div>
              </article>
            )}
          </section>
          <section className="panel">
            <PanelTitle
              icon={Archive}
              title="Audit trail"
              subtitle="Recent accountable actions"
            />
            <div className="audit-list">
              {audit.slice(0, 12).map((entry, index) => (
                <article key={String(entry.id ?? index)}>
                  <strong>{String(entry.action ?? "Recorded action")}</strong>
                  <span>{String(entry.approved_by ?? "System")}</span>
                  <small>{formatTime(String(entry.timestamp ?? ""))}</small>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}

function About() {
  return (
    <>
      <PageHeader eyebrow="Reference" title="How Ngeebula plans access">
        A bounded decision-support tool for access planners and works
        controllers—not an operational safety authority.
      </PageHeader>
      <section className="about-grid">
        <article className="panel">
          <PanelTitle
            icon={CircleHelp}
            title="The problem"
            subtitle="A constrained weekly access plan"
          />
          <p>
            Schedule every contract activity across the Alpha and Beta lines
            while preserving workload, planned starts, possessions, closures,
            buffers, weekly allocations and workfront limits.
          </p>
        </article>
        <article className="panel">
          <PanelTitle
            icon={Settings2}
            title="The method"
            subtitle="Constraint optimization with validation"
          />
          <p>
            A bounded constructive heuristic searches candidate orderings and
            ECLO choices. It can return an unresolved result and does not prove
            global optimality or infeasibility. Export is enabled only for a
            complete plan that passes the independent local checks.
          </p>
        </article>
        <article className="panel">
          <PanelTitle
            icon={GitCompareArrows}
            title="The scenarios"
            subtitle="Three transparent policy choices"
          />
          <p>
            A holds supply rigid. B holds dates rigid. C balances controlled
            supply elasticity against priority-weighted delay. Lower score is
            better only among feasible plans for the same scenario.
          </p>
        </article>
        <article className="panel">
          <PanelTitle
            icon={Info}
            title="Data boundaries"
            subtitle="Exact identifiers, honest provenance"
          />
          <p>
            The supplied pack contains 14 contracts, 54 activities and 192 work
            units on an abstract Alpha/Beta network. The project owner identifies
            it as SMRT-supplied; the public source does not establish that it
            reproduces live operations.
          </p>
        </article>
      </section>
      <section className="two-column about-evidence">
        <article className="panel">
          <h2>Source and rule limits</h2>
          <p>
            The eight CSV files are pinned to upstream commit <code>16526c0</code>.
            The organisers' official trackaccess validator is absent from that
            pack, so local validation is not certification or operational approval.
            Plans extending beyond the supplied horizon assume the final nominal
            weekly capacities continue; the interface reports that interpretation.
            The model does not cover mobilisation, extraction, fatigue, permits,
            authentication, live possessions or tamper-proof audit storage.
          </p>
          <p>
            <a href="https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement/tree/16526c02579c7f37e54eaaa42a4cc6d4ceb19994/PS1" target="_blank" rel="noreferrer">Pinned PS1 source</a>
          </p>
        </article>
        <article className="panel">
          <h2>Two separate planning engines</h2>
          <p>
            PS1 uses the bounded heuristic for weekly access, spatial buffers,
            workfronts and scenario scoring. The secondary maintenance workflow
            uses OR-Tools CP-SAT for minute-level crew and repair windows. Optional
            Gemini may classify unanchored repair text; it never schedules,
            approves, or receives PS1 inputs implicitly.
          </p>
        </article>
      </section>
      <section className="panel source-list">
        <h2>Why structured access planning matters</h2>
        <p>These public sources provide context for the planning problem. They do not validate this prototype or establish measured benefits.</p>
        <ul>
          <li><a href="https://www.channelnewsasia.com/singapore/tough-work-smrt-workers-train-rail-maintenance-5022391" target="_blank" rel="noreferrer">CNA, 1 April 2025</a> — observed overnight rail replacement within a narrow work period, including equipment movement and site access.</li>
          <li><a href="https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/12/news-releases/rail_reliability_taskforce_submits_its_recommendations.html" target="_blank" rel="noreferrer">LTA, SMRT and SBS Transit, 30 December 2025</a> — recommended more engineering hours and standardised condition monitoring.</li>
          <li><a href="https://www.mot.gov.sg/news-resources/newsroom/opening-remarks-by-acting-minister-for-transport-jeffrey-siow-at-sbs-transit-s-international-metro-operators--summit/" target="_blank" rel="noreferrer">Ministry of Transport, 19 November 2025</a> — described shutdown-window constraints and equipment movement.</li>
        </ul>
      </section>
      <section className="panel">
        <h2>Planning sequence</h2>
        <ol className="steps">
          <li>
            <span>1</span>
            <div>
              <strong>Import and inspect</strong>
              <p>Validate the instance and confirm its horizon.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>Choose a policy</strong>
              <p>Understand which planning lever may flex.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>Generate and validate</strong>
              <p>Hard rules gate feasibility before scoring.</p>
            </div>
          </li>
          <li>
            <span>4</span>
            <div>
              <strong>Review exact values</strong>
              <p>Use the timeline and table before export.</p>
            </div>
          </li>
        </ol>
      </section>
    </>
  );
}

function WarningList({ items }: { items: string[] }) {
  return (
    <ul className="warning-list">
      {items.map((x, i) => (
        <li key={i}>
          <AlertTriangle aria-hidden />
          {x}
        </li>
      ))}
    </ul>
  );
}
function formatTime(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : new Intl.DateTimeFormat("en-SG", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Singapore",
      }).format(d);
}
function formatBytes(n: number) {
  return n < 1024
    ? `${n} B`
    : n < 1048576
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1048576).toFixed(1)} MB`;
}
function formatPositions(value: unknown[]) {
  if (!value.length) return "Not scheduled";
  return value.map((item) => {
    if (!Array.isArray(item)) return String(item);
    const [week, eclo, night] = item;
    return `Week ${week}, ${Number(eclo) ? "ECLO" : `night ${night}`}`;
  }).join("; ");
}

export default App;
