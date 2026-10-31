import { useEffect, useState } from "react";
import { getDashboard } from "../api";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
  }, []);

  function load() {
    setError(null);
    getDashboard().then(setData).catch((err) => setError(err.message));
  }

  if (error) return <div className="screen"><p className="status error">{error}</p></div>;
  if (!data) return <div className="screen"><p className="status">Loading…</p></div>;

  const maxCategoryCount = Math.max(1, ...data.by_category.map((c) => c.count));

  return (
    <div className="screen">
      <div className="dashboard-header">
        <h2>Dashboard</h2>
        <button onClick={load}>Refresh</button>
      </div>

      <div className="tiles">
        <Tile label="Total calls" value={data.total_calls} />
        <Tile label="Courtroom runs" value={data.courtroom_runs} />
        <Tile label="Reused verdicts" value={data.reused} />
        <Tile label="Courtroom calls saved" value={data.calls_saved} />
      </div>

      <div className="card">
        <h3>Complaints by category</h3>
        {data.by_category.length === 0 && <p className="status">No calls yet.</p>}
        {data.by_category.map((row) => (
          <div className="bar-row" key={row.category}>
            <span className="bar-label">{row.category}</span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${(row.count / maxCategoryCount) * 100}%` }}
              />
            </div>
            <span className="bar-count">{row.count}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Risk split</h3>
        <div className="badge-row">
          {data.by_risk.map((row) => (
            <span className={`badge risk-${row.risk_level}`} key={row.risk_level}>
              {row.risk_level}: {row.count}
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Recurring issues</h3>
        {data.recurring_issues.length === 0 && <p className="status">None yet.</p>}
        <ul>
          {data.recurring_issues.map((row) => (
            <li key={`${row.category}-${row.subcategory}`}>
              {row.category} :: {row.subcategory} — {row.count} calls
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h3>Recent calls</h3>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Category</th>
              <th>Risk</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_calls.map((call) => (
              <tr key={call.id}>
                <td>{new Date(call.created_at).toLocaleTimeString()}</td>
                <td>{call.category} :: {call.subcategory}</td>
                <td>{call.risk_level}</td>
                <td>{call.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}