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

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

function stateLabel(state: string): string {
  return state.toLowerCase().replaceAll("_", " ");
}

function JobList({ jobs, selected, onSelect }: {
  jobs: JobSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (!jobs.length) return <p className="muted">No jobs have been recorded.</p>;
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <li key={job.id}>
          <button type="button" aria-pressed={selected === job.id} onClick={() => onSelect(job.id)}>
            <strong>{job.title}</strong>
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
  return (
    <article aria-labelledby="job-heading">
      <div className="detail-heading">
        <h2 id="job-heading">{detail.job.title}</h2>
        <span className="state">{stateLabel(detail.job.state)}</span>
      </div>
      <p className="muted">Execution ID <code>{detail.job.id}</code></p>
      <section aria-labelledby="graph-heading">
        <h3 id="graph-heading">Workflow dependencies</h3>
        {analysis.status === "invalid" &&
          <p role="status">{analysis.node} {graphErrors[analysis.reason]}. Showing the recorded task order.</p>}
        {orderedTasks.length > 0 && <div className="filters task-filter">
          <label>Search tasks
            <input type="search" value={taskQuery} onChange={(event) => setTaskQuery(event.target.value)} />
          </label>
        </div>}
        {visibleTasks.length ? (
          <ul className="workflow">
            {visibleTasks.map((task) => (
              <li key={task.id}>
                <div className="node">
                  <strong>{task.id}</strong>
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
        <h3 id="qa-heading">Integration QA</h3>
        {detail.candidate && <p>Candidate <code>{detail.candidate}</code></p>}
        {detail.qa.length ? <ol>{detail.qa.map((check) => (
          <li key={check.index}>Check {check.index} · exit code {check.exitCode}</li>
        ))}</ol> : <p className="muted">No integration QA results.</p>}
      </section>
      <section aria-labelledby="activity-heading">
        <h3 id="activity-heading">Recent activity</h3>
        {detail.events.length ? <ul className="events">{detail.events.map((event) => (
          <li key={event.sequence}>
            <time>{time.format(event.at * 1000)}</time>
            <span>{event.taskId && <><strong>{event.taskId}</strong>{" · "}</>}{event.type}</span>
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
  const visible = dashboard?.jobs.filter(({ title, id, state }) =>
    (!stateFilter || state === stateFilter) && (title.toLowerCase().includes(needle) || id.includes(needle)));

  return (
    <>
      <header>
        <div className="header-inner">
          <h1>Model Orchestration</h1>
          <p>Execution history. Open the Tk workspace to submit jobs, manage connections, or approve changes.</p>
        </div>
      </header>
      <main>
        {!response && available && <p role="status">Loading job history…</p>}
        {available && response?.status === "empty" && <p role="status">No legacy data found. Create a job in the Tk workspace to populate this dashboard.</p>}
        {!available && <p role="status">
          {dashboard ? "History unavailable. Showing the last loaded snapshot while the app reconnects." :
            "Job history is unavailable or incompatible. The app will retry."}
        </p>}
        {dashboard && observedAt && <p className="muted history-freshness">
          {available ? "Last refreshed " : "Cached snapshot from "}
          <time dateTime={observedAt.toISOString()}>{date.format(observedAt)} · {time.format(observedAt)}</time>
        </p>}
        {dashboard && (
          <div className="dashboard">
            <aside aria-labelledby="jobs-heading">
              <h2 id="jobs-heading">Job history</h2>
              <div className="filters">
                <label>Search job history
                  <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
                </label>
                <label>Job state
                  <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                    <option value="">All states</option>
                    {[...new Set([...states, stateFilter])].filter(Boolean).map((state) =>
                      <option key={state} value={state}>{stateLabel(state)}</option>)}
                  </select>
                </label>
              </div>
              {!visible?.length && dashboard.jobs.length > 0 ? <p>No jobs match these filters.</p> :
                <JobList jobs={visible ?? []} selected={selected} onSelect={setSelected} />}
            </aside>
            <div className="workspace">
              {detail ? <JobDetails key={detail.job.id} detail={detail} /> :
                <p className="muted">{!selected ? "Select a job to view its workflow and activity." :
                  !available ? "Job details will load when history is available." :
                  loadedFor === selected ? "This job is no longer available." : "Loading job details…"}</p>}
            </div>
          </div>
        )}
      </main>
    </>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Desktop root is missing");
createRoot(root).render(<App />);
