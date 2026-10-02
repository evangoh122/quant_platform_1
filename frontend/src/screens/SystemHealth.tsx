import { api } from '../api/client';
import type { AnalyticsResponse, Envelope, HealthResponse, AnalyticsItem } from '../api/types';
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

export function SystemHealth() {
  const health = useApi<HealthResponse>(() => api.health());
  const analytics = useApi<AnalyticsResponse>(() => api.analytics());

  const degraded = health.data?.dependencies.filter((d) => !d.ok).length ?? 0;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Analytics / System Health</h1>

      {health.loading && <LoadingState />}
      {health.error && <ErrorState message={health.error} onRetry={health.reload} />}
      {!health.loading && !health.error && health.data && (
        <Card title="Dependencies" subtitle={`v${health.data.version} · ${health.data.status}`}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Status" value={health.data.status} />
            <StatTile label="Degraded" value={degraded.toString()} />
            {health.data.dependencies.map((d) => (
              <StatTile key={d.name} label={d.name} value={d.ok ? 'ok' : 'down'} hint={d.detail} />
            ))}
          </div>
        </Card>
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
