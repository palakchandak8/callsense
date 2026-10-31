import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { getDashboard } from "../api";

const RISK_COLORS = { low: "#1f9d55", medium: "#d98c12", high: "#e3463a" };
const CAT_COLORS = ["#00a3dc", "#7c6cf0", "#20c997", "#f5a623", "#ef5da8", "#4cd9c0"];

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

      <div className="chart-grid">
        <div className="card">
          <h3>Complaints by category</h3>
          {data.by_category.length === 0 ? (
            <p className="status">No calls yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(180, data.by_category.length * 48)}>
              <BarChart data={data.by_category} layout="vertical" margin={{ left: 24, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis type="number" allowDecimals={false} stroke="var(--muted)" fontSize={12} />
                <YAxis type="category" dataKey="category" width={150} stroke="var(--muted)" fontSize={12} />
                <Tooltip
                  contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)" }}
                  cursor={{ fill: "var(--accent-soft)" }}
                />
                <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                  {data.by_category.map((_, i) => (
                    <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h3>Risk split</h3>
          {data.by_risk.length === 0 ? (
            <p className="status">No calls yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={data.by_risk}
                  dataKey="count"
                  nameKey="risk_level"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {data.by_risk.map((row) => (
                    <Cell key={row.risk_level} fill={RISK_COLORS[row.risk_level] || "#00a3dc"} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)" }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
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