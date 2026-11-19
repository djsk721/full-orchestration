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
  const analysis = analyzeDag(detail.tasks);
  const tasks = new Map(detail.tasks.map((task) => [task.id, task]));
  const orderedTasks = analysis.status === "valid"
    ? analysis.order.flatMap((id) => {
        const task = tasks.get(id);
        return task ? [task] : [];
      })
    : detail.tasks;
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
      <section aria-labelledby="graph-heading">
        <h3 id="graph-heading">Workflow dependencies</h3>
        {analysis.status === "invalid" &&
          <p role="status">{analysis.node} {graphErrors[analysis.reason]}. Showing the recorded task order.</p>}
        {orderedTasks.length ? (
          <ul className="workflow">
            {orderedTasks.map((task) => (
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
        ) : <p className="muted">No task records.</p>}
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

  useEffect(() => {
    let active = true;
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const current = await window.orchestration.snapshot(selected);
        if (active) setResponse(current);
      } catch {
        if (active) setResponse({ status: "unavailable" });
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

  return (
    <>
      <header>
        <div className="header-inner">
          <h1>Model Orchestration</h1>
          <p>Read-only preview. Use the Python desktop to run jobs or approve changes.</p>
        </div>
      </header>
      <main>
        {!response && <p role="status">Loading job history…</p>}
        {response?.status === "empty" && <p role="status">No legacy data found. Create a job in the Python desktop to populate this dashboard.</p>}
        {response?.status === "unavailable" && <p role="status">The legacy database is unavailable or incompatible. The dashboard will retry.</p>}
        {dashboard && (
          <div className="dashboard">
            <aside aria-labelledby="jobs-heading">
              <h2 id="jobs-heading">Job history</h2>
              <JobList jobs={dashboard.jobs} selected={selected} onSelect={setSelected} />
            </aside>
            <div className="workspace">
              {detail ? <JobDetails detail={detail} /> :
                <p className="muted">{selected ? "Loading job details…" : "Select a job to view its workflow and activity."}</p>}
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
