import { api } from '../api/client';
import type { AnalyticsResponse, Envelope, HealthResponse, HealthTraceResponse, AnalyticsItem, TraceEvent } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

function AnalyticsSection({ title, envelope }: { title: string; envelope: Envelope<AnalyticsItem> }) {
  return (
    <Card title={title} subtitle={envelope.source} actions={<FreshnessBadge freshness={envelope.freshness} />}>
      {envelope.empty ? (
        <EmptyState title={`No ${title.toLowerCase()} yet`} detail={`${envelope.source} is empty — metrics appear once the analytics pipeline populates it.`} />
      ) : (
        <ul className="space-y-1 text-sm">
          {envelope.data.map((item) => (
            <li key={item.metric} className="flex justify-between">
              <span className="text-slate-600 dark:text-slate-300">{item.metric || item.detail}</span>
              <span className="font-medium">{item.value?.toString() ?? '—'}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function SlowStagesList({ events }: { events: TraceEvent[] }) {
  if (events.length === 0) return null;
  return (
    <Card title="Slowest Recent Stages" subtitle={`${events.length} slow event(s) > 2s`}>
      <ul className="space-y-1 text-sm">
        {events.map((e, i) => (
          <li key={i} className="flex justify-between">
            <span className="text-slate-600 dark:text-slate-300">
              {e.ok ? '' : '! '}{e.name}
              {e.error ? ` (${e.error})` : ''}
            </span>
            <span className="font-medium">{e.elapsed_ms.toFixed(0)}ms</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DependencyCard({ d }: { d: { name: string; ok: boolean; detail: string; latency_ms: number | null; last_error: string | null; last_ok_at: number | null; circuit_breaker_state: string | null } }) {
  const lastOk = d.last_ok_at ? new Date(d.last_ok_at * 1000).toLocaleTimeString() : 'never';
  return (
    <div className="rounded border p-3 space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-medium">{d.name}</span>
        <span className={d.ok ? 'text-green-600' : 'text-red-600'}>{d.ok ? 'ok' : 'down'}</span>
      </div>
      <div className="text-xs text-slate-500 space-y-0.5">
        <div>Latency: {d.latency_ms != null ? `${d.latency_ms.toFixed(0)}ms` : '—'}</div>
        {d.last_error && <div className="text-red-500">Error: {d.last_error}</div>}
        <div>Last OK: {lastOk}</div>
        {d.circuit_breaker_state && <div>CB: {d.circuit_breaker_state}</div>}
      </div>
    </div>
  );
}

export function SystemHealth() {
  const health = useApi<HealthResponse>(() => api.health());
  const trace = useApi<HealthTraceResponse>(() => api.healthTrace());
  const analytics = useApi<AnalyticsResponse>(() => api.analytics());

  const degraded = health.data?.dependencies.filter((d) => !d.ok).length ?? 0;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Analytics / System Health</h1>

      {health.loading && <LoadingState />}
      {health.error && <ErrorState message={health.error} onRetry={health.reload} />}
      {!health.loading && !health.error && health.data && (
        <>
          <Card title="Dependencies" subtitle={`v${health.data.version} · ${health.data.status}`}>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 mb-3">
              <StatTile label="Status" value={health.data.status} />
              <StatTile label="Degraded" value={degraded.toString()} />
              <StatTile label="Role Cache" value={health.data.role_cache_size.toString()} />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {health.data.dependencies.map((d) => (
                <DependencyCard key={d.name} d={d} />
              ))}
            </div>
          </Card>

          {health.data.startup.length > 0 && (
            <Card title="Startup Stages">
              <ul className="space-y-1 text-sm">
                {health.data.startup.map((s, i) => (
                  <li key={i} className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-300">{s.name}</span>
                    <span className="font-medium">{s.elapsed_ms.toFixed(0)}ms</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      {trace.loading && <LoadingState />}
      {trace.error && <ErrorState message={trace.error} onRetry={trace.reload} />}
      {!trace.loading && !trace.error && trace.data && (
        <SlowStagesList events={trace.data.slow} />
      )}

      {analytics.loading && <LoadingState />}
      {analytics.error && <ErrorState message={analytics.error} onRetry={analytics.reload} />}
      {!analytics.loading && !analytics.error && analytics.data && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <AnalyticsSection title="Model Performance" envelope={analytics.data.model_performance} />
          <AnalyticsSection title="Agent Activity" envelope={analytics.data.agent_activity} />
          <AnalyticsSection title="Latency (p50/p95)" envelope={analytics.data.latency} />
          <AnalyticsSection title="Stream Freshness" envelope={analytics.data.stream_freshness} />
        </div>
      )}
    </div>
  );
}