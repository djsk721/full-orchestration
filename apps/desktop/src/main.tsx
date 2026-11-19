import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { DashboardResponse, DesktopApi, JobDetail, JobSummary } from "./contracts";
import { analyzeDag } from "../core/dag";
import "./styles.css";

declare global {
  interface Window {
    orchestration: DesktopApi;
  }
}

type Tone = "info" | "success" | "warning" | "danger" | "neutral";

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

function stateLabel(state: string): string {
  return state.toLowerCase().replaceAll("_", " ");
}

function stateTone(state: string): Tone {
  const upper = state.toUpperCase();
  if (["SUCCEEDED", "APPROVED", "MERGED", "COMPLETED"].includes(upper)) return "success";
  if (["AWAITING_APPROVAL", "PENDING", "PAUSED"].includes(upper)) return "warning";
  if (["FAILED", "REJECTED", "CANCELLED", "TIMED_OUT"].includes(upper)) return "danger";
  if (["RUNNING", "VERIFYING", "EXECUTING", "CLAIMED", "INTEGRATING"].includes(upper)) return "info";
  return "neutral";
}

function summarizeJobs(jobs: JobSummary[]) {
  let active = 0;
  let awaiting = 0;
  let succeeded = 0;
  let failed = 0;
  for (const job of jobs) {
    const upper = job.state.toUpperCase();
    if (["RUNNING", "VERIFYING", "EXECUTING", "CLAIMED", "INTEGRATING", "QUEUED", "PENDING"].includes(upper)) {
      active += 1;
    } else if (upper === "AWAITING_APPROVAL") {
      awaiting += 1;
    } else if (["SUCCEEDED", "APPROVED", "MERGED", "COMPLETED"].includes(upper)) {
      succeeded += 1;
    } else if (["FAILED", "REJECTED", "CANCELLED", "TIMED_OUT"].includes(upper)) {
      failed += 1;
    }
  }
  return { total: jobs.length, active, awaiting, succeeded, failed };
}

function JobList({ jobs, selected, onSelect }: {
  jobs: JobSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (!jobs.length) return <p className="muted empty-hint">No jobs have been recorded.</p>;
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <li key={job.id}>
          <button type="button" aria-pressed={selected === job.id} onClick={() => onSelect(job.id)}>
            <div className="job-card-top">
              <strong>{job.title}</strong>
              <span className={`pill pill-sm tone-${stateTone(job.state)}`}>{stateLabel(job.state)}</span>
            </div>
            <span>{stateLabel(job.state)} · {job.background ? "Background" : "Foreground"}</span>
            <time>{dateTime.format(job.updatedAt * 1000)}</time>
          </button>
        </li>
      ))}
    </ul>
  );
}

function JobDetails({ detail }: { detail: JobDetail }) {
  const [taskQuery, setTaskQuery] = useState("");
  const analysis = analyzeDag(detail.tasks);
  const tasks = new Map(detail.tasks.map((task) => [task.id, task]));
  const orderedTasks = analysis.status === "valid"
    ? analysis.order.flatMap((id) => {
        const task = tasks.get(id);
        return task ? [task] : [];
      })
    : detail.tasks;
  const filter = taskQuery.trim().toLowerCase();
  const visibleTasks = orderedTasks.filter(({ id, role }) =>
    id.toLowerCase().includes(filter) || role.toLowerCase().includes(filter));
  const graphErrors = {
    duplicate: "has a duplicate task ID",
    "unknown-dependency": "references a missing task",
    cycle: "belongs to a workflow with a dependency cycle",
  };
  const passedChecks = detail.qa.filter((check) => check.exitCode === 0).length;
  const failedChecks = detail.qa.length - passedChecks;

  return (
    <article aria-labelledby="job-heading">
      <div className="detail-heading">
        <div>
          <h2 id="job-heading">{detail.job.title}</h2>
          <p className="muted detail-meta">
            Execution ID <code>{detail.job.id}</code> · {detail.job.background ? "Background run" : "Foreground run"}
          </p>
        </div>
        <span className={`state pill tone-${stateTone(detail.job.state)}`}>{stateLabel(detail.job.state)}</span>
      </div>
      <section aria-labelledby="graph-heading">
        <div className="section-head">
          <h3 id="graph-heading">Workflow dependencies</h3>
          {orderedTasks.length > 0 && <span className="muted section-count">{orderedTasks.length} tasks</span>}
        </div>
        {analysis.status === "invalid" &&
          <p role="status" className="banner banner-warning">{analysis.node} {graphErrors[analysis.reason]}. Showing the recorded task order.</p>}
        {orderedTasks.length > 0 && <div className="filters task-filter">
          <label>Search tasks
            <input type="search" value={taskQuery} onChange={(event) => setTaskQuery(event.target.value)} placeholder="Filter by task ID or role" />
          </label>
        </div>}
        {visibleTasks.length ? (
          <ul className="workflow">
            {visibleTasks.map((task) => (
              <li key={task.id} className={`tone-border-${stateTone(task.state)}`}>
                <div className="node">
                  <div className="node-title">
                    <span className={`tone-dot tone-${stateTone(task.state)}`} aria-hidden="true" />
                    <strong>{task.id}</strong>
                  </div>
                  <span>{task.role} · {stateLabel(task.state)} · attempt {task.attempt}</span>
                </div>
                <p className="dependency">
                  {task.dependencies.length ? <>Depends on {task.dependencies.join(", ")}</> : "Starts the workflow"}
                </p>
              </li>
            ))}
          </ul>
        ) : <p className="muted">{orderedTasks.length ? "No tasks match this search." : "No task records."}</p>}
      </section>
      <section aria-labelledby="qa-heading">
        <div className="section-head">
          <h3 id="qa-heading">Integration QA</h3>
          {detail.qa.length > 0 && (
            <span className={`pill pill-sm ${failedChecks > 0 ? "tone-danger" : "tone-success"}`}>
              {passedChecks}/{detail.qa.length} passed
            </span>
          )}
        </div>
        {detail.candidate && <p className="candidate-sha">Candidate <code>{detail.candidate}</code></p>}
        {detail.qa.length ? <ol className="qa-list">{detail.qa.map((check) => (
          <li key={check.index} className={check.exitCode === 0 ? "qa-item qa-pass" : "qa-item qa-fail"}>
            <span>Check {check.index} · exit code {check.exitCode}</span>
            <span className={`pill pill-sm ${check.exitCode === 0 ? "tone-success" : "tone-danger"}`}>
              {check.exitCode === 0 ? "PASS" : "FAIL"}
            </span>
          </li>
        ))}</ol> : <p className="muted">No integration QA results.</p>}
      </section>
      <section aria-labelledby="activity-heading">
        <div className="section-head">
          <h3 id="activity-heading">Recent activity</h3>
          {detail.events.length > 0 && <span className="muted section-count">{detail.events.length} events</span>}
        </div>
        {detail.events.length ? <ul className="events">{detail.events.map((event) => (
          <li key={event.sequence}>
            <time>{time.format(event.at * 1000)}</time>
            <span className="event-body">{event.taskId && <><strong>{event.taskId}</strong>{" · "}</>}{event.type}</span>
          </li>
        ))}</ul> : <p className="muted">No activity has been recorded.</p>}
      </section>
    </article>
  );
}

function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const [response, setResponse] = useState<DashboardResponse | null>(null);
  const [available, setAvailable] = useState(true);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [observedAt, setObservedAt] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");

  useEffect(() => {
    let active = true;
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const current = await window.orchestration.snapshot(selected);
        if (!active) return;
        setAvailable(current.status !== "unavailable");
        if (current.status !== "unavailable") {
          setResponse(current);
          setLoadedFor(selected);
          setObservedAt(new Date());
        }
      } catch {
        if (active) setAvailable(false);
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selected]);

  const dashboard = response?.status === "ready" ? response.dashboard : null;
  const detail = dashboard?.detail?.job.id === selected ? dashboard.detail : null;
  const states = [...new Set(dashboard?.jobs.map(({ state }) => state))].sort();
  const needle = query.trim().toLowerCase();
  const visible = dashboard?.jobs.filter(({ title, id, state, background }) =>
    (!stateFilter || state === stateFilter) &&
    (!modeFilter || (modeFilter === "background" ? background : !background)) &&
    (title.toLowerCase().includes(needle) || id.includes(needle)));
  const summary = summarizeJobs(dashboard?.jobs ?? []);

  return (
    <>
      <header>
        <div className="header-inner">
          <div className="header-top">
            <div className="header-title-group">
              <h1>Model Orchestration</h1>
              <span className="pill tone-neutral">Read-only Monitor</span>
              <span className={`pill ${!response && available ? "tone-info" : available ? "tone-success" : "tone-warning"}`}>
                {!response && available ? "Connecting" : available ? "Live Sync" : "Offline Cache"}
              </span>
            </div>
            {dashboard && observedAt && (
              <p className="muted history-freshness">
                {available ? "Last refreshed " : "Cached snapshot from "}
                <time dateTime={observedAt.toISOString()}>{date.format(observedAt)} · {time.format(observedAt)}</time>
              </p>
            )}
          </div>
          <p className="header-subtitle">Execution history. Open the Tk workspace to submit jobs, manage connections, or approve changes.</p>
        </div>
      </header>
      <main>
        {!response && available && <p role="status" className="banner banner-info">Loading job history…</p>}
        {available && response?.status === "empty" && (
          <p role="status" className="banner banner-info">
            No legacy data found. Create a job in the Tk workspace to populate this dashboard.
          </p>
        )}
        {!available && (
          <p role="status" className="banner banner-warning">
            {dashboard
              ? "History unavailable. Showing the last loaded snapshot while the app reconnects."
              : "Job history is unavailable or incompatible. The app will retry."}
          </p>
        )}
        {dashboard && (
          <>
            <section className="kpi-grid" aria-label="Execution overview">
              <div className="kpi-card">
                <span className="kpi-label">Total runs</span>
                <strong className="kpi-value">{summary.total}</strong>
              </div>
              <div className="kpi-card kpi-info">
                <span className="kpi-label">Running</span>
                <strong className="kpi-value">{summary.active}</strong>
              </div>
              <div className="kpi-card kpi-warning">
                <span className="kpi-label">Awaiting approval</span>
                <strong className="kpi-value">{summary.awaiting}</strong>
              </div>
              <div className="kpi-card kpi-success">
                <span className="kpi-label">Succeeded</span>
                <strong className="kpi-value">{summary.succeeded}</strong>
              </div>
              <div className="kpi-card kpi-danger">
                <span className="kpi-label">Failed / Stopped</span>
                <strong className="kpi-value">{summary.failed}</strong>
              </div>
            </section>
            <div className="dashboard">
              <aside aria-labelledby="jobs-heading">
                <div className="section-head">
                  <h2 id="jobs-heading">Job history</h2>
                  <span className="muted section-count">{visible?.length ?? 0}</span>
                </div>
                <div className="filters">
                  <label>Search job history
                    <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title or execution ID" />
                  </label>
                  <div className="filter-row">
                    <label>Job state
                      <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                        <option value="">All states</option>
                        {[...new Set([...states, stateFilter])].filter(Boolean).map((state) =>
                          <option key={state} value={state}>{stateLabel(state)}</option>)}
                      </select>
                    </label>
                    <label>Execution mode
                      <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value)}>
                        <option value="">All modes</option>
                        <option value="background">Background</option>
                        <option value="foreground">Foreground</option>
                      </select>
                    </label>
                  </div>
                </div>
                {!visible?.length && dashboard.jobs.length > 0 ? <p className="muted empty-hint">No jobs match these filters.</p> :
                  <JobList jobs={visible ?? []} selected={selected} onSelect={setSelected} />}
              </aside>
              <div className="workspace">
                {detail ? <JobDetails key={detail.job.id} detail={detail} /> :
                  <div className="workspace-empty">
                    <p className="muted">
                      {!selected
                        ? "Select a job to view its workflow and activity."
                        : !available
                          ? "Job details will load when history is available."
                          : loadedFor === selected
                            ? "This job is no longer available."
                            : "Loading job details…"}
                    </p>
                  </div>}
              </div>
            </div>
          </>
        )}
      </main>
    </>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Desktop root is missing");
createRoot(root).render(<App />);
