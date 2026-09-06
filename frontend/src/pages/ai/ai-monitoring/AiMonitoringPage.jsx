import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import styles from "./AiMonitoringPage.module.scss";
import MIcon from "../../../components/MIcon";
import LoadingState from "../../../components/LoadingState/LoadingState";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import { AiMonitoringService } from "../../../services/aiMonitoring";
import { useToast } from "../../../hooks/useToast";
import useAutoRefresh from "../../../hooks/useAutoRefresh";
import PageHeader from "../../../components/PageHeader/PageHeader";

export function presetToRange(preset) {
  const end = new Date();
  const start = new Date();
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  start.setDate(start.getDate() - days);
  return { startDate: start.toISOString(), endDate: end.toISOString() };
}

export function presetToBucket(preset) {
  return preset === "7d" ? "hour" : "day";
}

export function formatTokens(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatDuration(ms) {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export function formatModelDisplay(modelName) {
  if (!modelName) return "—";
  const trimmed = modelName.trim();
  if (!trimmed) return "—";

  const match = trimmed.match(/models--([^/]+)--([^/]+)/);
  if (match) return `${match[1]}/${match[2]}`;

  if (/^(?:[A-Za-z]:[\\/]|[\\/])/.test(trimmed)) {
    const separator = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
    const basename = separator >= 0 ? trimmed.slice(separator + 1) : trimmed;
    return basename || trimmed;
  }

  return trimmed;
}

export function isOkStatus(status) {
  return (
    status === "success" ||
    status === 200 ||
    status === "200" ||
    status === "ok"
  );
}

function formatNumber(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat("zh-TW").format(n);
}

function formatPercent(value) {
  if (value == null) return "—";
  return `${Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1)}%`;
}

function formatDelta(value, unit = "%") {
  if (value == null) return null;
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(number % 1 === 0 ? 0 : 1)}${unit}`;
}

function formatChartTime(value, bucket) {
  if (!value) return "—";
  const date = new Date(value);
  return date.toLocaleDateString(
    "zh-TW",
    bucket === "hour"
      ? { month: "numeric", day: "numeric", hour: "2-digit" }
      : { month: "numeric", day: "numeric" },
  );
}

function EmptyState({ icon, title }) {
  return <SharedEmptyState icon={icon} title={title} />;
}

function StatusBadge({ status }) {
  const { t } = useTranslation("ai");
  const ok = isOkStatus(status);
  return (
    <span className={`${styles.badge} ${ok ? styles.badge_ok : styles.badge_err}`}>
      <span className={styles.dot} />
      {ok ? t("AiMonitoringPage.statusSuccess") : t("AiMonitoringPage.statusFail")}
    </span>
  );
}

function UserCell({ email, fullName, fallback }) {
  return (
    <div className={styles.userCell}>
      <div className={styles.userName}>{fullName || fallback || "—"}</div>
      {email ? <div className={styles.userEmail}>{email}</div> : null}
    </div>
  );
}

function CallTypeCell({ callType, formatCallType }) {
  const label = formatCallType(callType);
  return (
    <div className={styles.callTypeCell}>
      <div className={styles.callTypeLabel}>{label}</div>
      {callType && label !== callType ? (
        <div className={styles.callTypeKey}>{callType}</div>
      ) : null}
    </div>
  );
}

function MetricCard({ icon, tone, label, value, detail, delta, deltaTone }) {
  return (
    <div className={styles.metricCard}>
      <div className={`${styles.metricIcon} ${styles[`metricIcon_${tone}`]}`}>
        <MIcon name={icon} size={19} />
      </div>
      <div className={styles.metricBody}>
        <span className={styles.metricLabel}>{label}</span>
        <span className={styles.metricValue}>{value}</span>
        <span className={`${styles.metricDetail} ${deltaTone ? styles[`metricDetail_${deltaTone}`] : ""}`}>
          {delta || detail}
        </span>
      </div>
    </div>
  );
}

function MetricGroupCard({ icon, tone, label, items }) {
  return (
    <div className={`${styles.metricCard} ${styles.metricGroupCard}`}>
      <div className={`${styles.metricIcon} ${styles[`metricIcon_${tone}`]}`}>
        <MIcon name={icon} size={19} />
      </div>
      <div className={styles.metricGroupBody}>
        <span className={styles.metricLabel}>{label}</span>
        <div className={styles.metricGroupItems}>
          {items.map((item) => (
            <div className={styles.metricItem} key={item.key}>
              <span className={styles.metricItemLabel}>{item.label}</span>
              <span className={styles.metricItemValue}>{item.value}</span>
              {item.delta || item.detail ? (
                <span className={`${styles.metricDetail} ${item.deltaTone ? styles[`metricDetail_${item.deltaTone}`] : ""}`}>
                  {item.delta || item.detail}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TrendTooltip({ active, payload, label, bucket, t }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipTitle}>{formatChartTime(row?.bucket_start ?? label, bucket)}</div>
      <div className={styles.tooltipRow}>
        <span>{t("AiMonitoringPage.chartCalls")}</span>
        <strong>{formatNumber(row?.total_calls)}</strong>
      </div>
      <div className={styles.tooltipRow}>
        <span>{t("AiMonitoringPage.chartFailed")}</span>
        <strong className={styles.tooltipDanger}>{formatNumber(row?.failed_calls)}</strong>
      </div>
      <div className={styles.tooltipRow}>
        <span>{t("AiMonitoringPage.chartErrorRate")}</span>
        <strong>{formatPercent(row?.error_rate)}</strong>
      </div>
      <div className={styles.tooltipRow}>
        <span>{t("AiMonitoringPage.chartLatency")}</span>
        <strong>{formatDuration(row?.avg_latency_ms)}</strong>
      </div>
    </div>
  );
}

function TrendChart({ series, bucket, loading, t }) {
  if (loading) return <LoadingState text={t("AiMonitoringPage.loadingTrend")} />;
  if (!series?.length) {
    return <EmptyState icon="show_chart" title={t("AiMonitoringPage.emptyTrendTitle")} />;
  }

  return (
    <div className={styles.chartFrame}>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={series} margin={{ top: 12, right: 12, left: -14, bottom: 4 }}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="bucket_start"
            tickFormatter={(value) => formatChartTime(value, bucket)}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            yAxisId="calls"
            allowDecimals={false}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <YAxis
            yAxisId="rate"
            orientation="right"
            domain={[0, "auto"]}
            tickFormatter={(value) => `${value}%`}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={42}
          />
          <Tooltip
            content={<TrendTooltip bucket={bucket} t={t} />}
            cursor={{ fill: "var(--color-hover)", opacity: 0.45 }}
          />
          <Legend
            verticalAlign="top"
            align="right"
            height={32}
            iconType="circle"
            wrapperStyle={{ color: "var(--color-text-secondary)", fontSize: 12 }}
          />
          <Bar
            yAxisId="calls"
            dataKey="failed_calls"
            name={t("AiMonitoringPage.chartFailed")}
            fill="var(--color-danger)"
            fillOpacity={0.75}
            radius={[4, 4, 0, 0]}
            maxBarSize={20}
          />
          <Line
            yAxisId="calls"
            type="monotone"
            dataKey="total_calls"
            name={t("AiMonitoringPage.chartCalls")}
            stroke="var(--color-primary)"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
          <Line
            yAxisId="rate"
            type="monotone"
            dataKey="error_rate"
            name={t("AiMonitoringPage.chartErrorRate")}
            stroke="var(--color-warning)"
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ModelStatusPanel({ runtime, error, loading, t }) {
  const gateway = runtime?.gateway;
  const gatewayStatus = error ? "unavailable" : gateway?.status ?? "unknown";
  const modelCount = error ? 0 : runtime?.models?.length ?? 0;
  const gatewayLabel = {
    available: t("AiMonitoringPage.runtimeAvailable"),
    degraded: t("AiMonitoringPage.runtimeDegraded"),
    unavailable: t("AiMonitoringPage.runtimeUnavailable"),
    not_configured: t("AiMonitoringPage.runtimeNotConfigured"),
    unknown: t("AiMonitoringPage.runtimeUnknown"),
  }[gatewayStatus] ?? t("AiMonitoringPage.runtimeUnknown");

  return (
    <section className={`${styles.panel} ${styles.runtimePanel}`} aria-labelledby="runtime-heading">
      <div className={styles.panelHeader}>
        <div>
          <h2 id="runtime-heading" className={styles.panelTitle}>
            <MIcon name="dns" size={18} />
            {t("AiMonitoringPage.runtimeTitle")}
          </h2>
          <p className={styles.panelDescription}>{t("AiMonitoringPage.runtimeDescription")}</p>
        </div>
        {runtime?.checked_at ? (
          <span className={styles.checkedAt}>
            {t("AiMonitoringPage.checkedAt", { time: new Date(runtime.checked_at).toLocaleTimeString("zh-TW") })}
          </span>
        ) : null}
      </div>

      <div className={`${styles.gatewayStatus} ${styles[`gatewayStatus_${gatewayStatus}`]}`}>
        <span className={styles.statusPulse} />
        <div>
          <strong>{gatewayLabel}</strong>
          <span>{!error && gateway?.readiness ? t("AiMonitoringPage.readinessReady") : t("AiMonitoringPage.readinessNotReady")}</span>
        </div>
      </div>

      {loading ? (
        <LoadingState text={t("AiMonitoringPage.loadingRuntime")} />
      ) : modelCount === 0 ? (
        <div className={styles.runtimeEmpty}>
          <MIcon name="help_outline" size={18} />
          <span>{error ? t("AiMonitoringPage.runtimeLoadError") : t("AiMonitoringPage.noModelDiscovery")}</span>
        </div>
      ) : (
        <div className={styles.modelList}>
          {runtime.models.map((model) => (
            <div className={styles.modelRow} key={model.name}>
              <span className={`${styles.modelDot} ${styles[`modelDot_${model.status}`]}`} />
              <div className={styles.modelInfo}>
                <strong title={model.name}>{formatModelDisplay(model.name)}</strong>
                <span>{t("AiMonitoringPage.deploymentCount", { healthy: model.healthy_deployments, unhealthy: model.unhealthy_deployments })}</span>
              </div>
              <span className={`${styles.modelStatus} ${styles[`modelStatus_${model.status}`]}`}>
                {t(`AiMonitoringPage.modelStatus_${model.status}`, { defaultValue: model.status })}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ModelBreakdown({ models, t, onModelSelect }) {
  if (!models?.length) {
    return <EmptyState icon="model_training" title={t("AiMonitoringPage.emptyModelBreakdown")} />;
  }

  return (
    <div className={styles.breakdownList}>
      {models.slice(0, 6).map((model) => (
        <button
          type="button"
          className={styles.breakdownRow}
          key={model.model_name}
          onClick={() => onModelSelect(model.model_name)}
        >
          <span className={styles.breakdownModel} title={model.model_name}>
            {formatModelDisplay(model.model_name)}
          </span>
          <span className={styles.breakdownCalls}>{formatNumber(model.total_calls)}</span>
          <span className={styles.breakdownTokens}>{formatTokens(model.total_tokens)}</span>
          <span className={`${styles.breakdownRate} ${model.error_rate > 0 ? styles.breakdownRateDanger : ""}`}>
            {formatPercent(model.error_rate)}
          </span>
        </button>
      ))}
    </div>
  );
}

function StatusBanner({ overview, runtime, overviewError, runtimeError, t }) {
  const errorRate = overview?.summary?.error_rate;
  const errorDelta = overview?.comparison?.error_rate_delta;
  let tone = "neutral";
  let icon = "info";
  let message = t("AiMonitoringPage.summaryNoData");

  if (overviewError) {
    tone = "danger";
    icon = "error_outline";
    message = t("AiMonitoringPage.summaryLoadError");
  } else if (runtimeError) {
    tone = "warning";
    icon = "cloud_off";
    message = t("AiMonitoringPage.summaryRuntimeError");
  } else if (errorRate != null && errorDelta != null && errorDelta > 0.5) {
    tone = "warning";
    icon = "trending_up";
    message = t("AiMonitoringPage.summaryWorsening", { delta: formatDelta(errorDelta, "pp") });
  } else if (errorRate != null) {
    tone = "success";
    icon = "check_circle";
    message = t("AiMonitoringPage.summaryStable", { rate: formatPercent(errorRate) });
  }

  if (runtime?.summary?.offline > 0 && !overviewError) {
    tone = "danger";
    icon = "report_problem";
    message = t("AiMonitoringPage.summaryOfflineModels", { count: runtime.summary.offline });
  }

  return (
    <div className={`${styles.statusBanner} ${styles[`statusBanner_${tone}`]}`} role="status">
      <MIcon name={icon} size={20} />
      <span>{message}</span>
    </div>
  );
}

function DetailTable({ tab, calls, users, query, failedOnly, t }) {
  const CALL_TYPE_LABELS = {
    recommend: t("AiMonitoringPage.callTypeRecommend"),
    chat: t("AiMonitoringPage.callTypeChat"),
    ai_nav: t("AiMonitoringPage.callTypeAiNav"),
    tj_rubric: t("AiMonitoringPage.callTypeTjRubric"),
    tj_chat: t("AiMonitoringPage.callTypeTjChat"),
    tj_script_gen: t("AiMonitoringPage.callTypeTjScriptGen"),
    tj_script_review: t("AiMonitoringPage.callTypeTjScriptReview"),
    tj_result_ai: t("AiMonitoringPage.callTypeTjResultAi"),
  };
  const formatCallType = (callType) => callType ? CALL_TYPE_LABELS[callType] ?? callType : "—";
  const q = query.trim().toLowerCase();

  if (tab === "users") {
    const visibleUsers = (users ?? []).filter((user) => {
      if (!q) return true;
      return (user.user_email ?? "").toLowerCase().includes(q)
        || (user.user_full_name ?? "").toLowerCase().includes(q);
    });
    if (!visibleUsers.length) return <EmptyState icon="groups" title={t("AiMonitoringPage.emptyUsersTitle")} />;
    return (
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr>
            <th className={styles.th}>{t("AiMonitoringPage.colUser")}</th>
            <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colCallCount")}</th>
            <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colTokensTotal")}</th>
            <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colAvgLatency")}</th>
            <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colFailRate")}</th>
          </tr></thead>
          <tbody>{visibleUsers.map((user) => {
            const totalCalls = (user.proxy_calls ?? 0) + (user.template_calls ?? 0);
            const totalTokens = (user.proxy_input_tokens ?? 0) + (user.proxy_output_tokens ?? 0)
              + (user.template_input_tokens ?? 0) + (user.template_output_tokens ?? 0);
            return <tr key={user.user_id} className={styles.tr}>
              <td className={styles.td}><UserCell email={user.user_email} fullName={user.user_full_name} fallback={user.user_id} /></td>
              <td className={`${styles.td} ${styles.numericCell}`}>{formatNumber(totalCalls)}</td>
              <td className={`${styles.td} ${styles.numericCell}`}>{formatTokens(totalTokens)}</td>
              <td className={`${styles.td} ${styles.numericCell}`}>{formatDuration(user.avg_latency_ms)}</td>
              <td className={`${styles.td} ${styles.numericCell}`}>{formatPercent(user.error_rate)}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  const source = tab === "proxy" ? calls.proxy : calls.template;
  const visibleCalls = (source ?? []).filter((call) => {
    if (failedOnly && isOkStatus(call.status)) return false;
    if (!q) return true;
    return (call.user_email ?? "").toLowerCase().includes(q)
      || (call.user_full_name ?? "").toLowerCase().includes(q)
      || (call.model_name ?? "").toLowerCase().includes(q)
      || (call.call_type ?? "").toLowerCase().includes(q)
      || formatCallType(call.call_type).toLowerCase().includes(q)
      || (call.request_type ?? "").toLowerCase().includes(q)
      || (call.preset ?? "").toLowerCase().includes(q);
  });

  if (!visibleCalls.length) return <EmptyState icon="analytics" title={t("AiMonitoringPage.emptyCallsTitle")} />;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead><tr>
          <th className={styles.th}>{t("AiMonitoringPage.colTime")}</th>
          <th className={styles.th}>{t("AiMonitoringPage.colUser")}</th>
          {tab === "proxy" ? <>
            <th className={styles.th}>{t("AiMonitoringPage.colModel")}</th>
            <th className={styles.th}>{t("AiMonitoringPage.colType")}</th>
          </> : <>
            <th className={styles.th}>{t("AiMonitoringPage.colCallType")}</th>
            <th className={styles.th}>{t("AiMonitoringPage.colModel")}</th>
            <th className={styles.th}>{t("AiMonitoringPage.colPreset")}</th>
          </>}
          <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colInput")}</th>
          <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colOutput")}</th>
          <th className={`${styles.th} ${styles.thRight}`}>{t("AiMonitoringPage.colDuration")}</th>
          <th className={styles.th}>{t("AiMonitoringPage.colStatus")}</th>
        </tr></thead>
        <tbody>{visibleCalls.map((call) => <tr key={call.id} className={`${styles.tr} ${!isOkStatus(call.status) ? styles.trFailed : ""}`}>
          <td className={styles.td}>{call.created_at ? new Date(call.created_at).toLocaleString("zh-TW") : "—"}</td>
          <td className={styles.td}><UserCell email={call.user_email} fullName={call.user_full_name} fallback={call.user_id} /></td>
          {tab === "proxy" ? <>
            <td className={`${styles.td} ${styles.monoCell}`} title={call.model_name}>{formatModelDisplay(call.model_name)}</td>
            <td className={styles.td}>{call.request_type ?? "—"}</td>
          </> : <>
            <td className={styles.td}><CallTypeCell callType={call.call_type} formatCallType={formatCallType} /></td>
            <td className={`${styles.td} ${styles.monoCell}`} title={call.model_name}>{formatModelDisplay(call.model_name)}</td>
            <td className={styles.td}>{call.preset ?? "—"}</td>
          </>}
          <td className={`${styles.td} ${styles.numericCell}`}>{formatTokens(call.input_tokens ?? 0)}</td>
          <td className={`${styles.td} ${styles.numericCell}`}>{formatTokens(call.output_tokens ?? 0)}</td>
          <td className={`${styles.td} ${styles.numericCell}`}>{formatDuration(call.request_duration_ms)}</td>
          <td className={styles.td}><StatusBadge status={call.status} /></td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}

export default function AiMonitoringPage() {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const [preset, setPreset] = useState("7d");
  const [detailTab, setDetailTab] = useState("proxy");
  const [query, setQuery] = useState("");
  const [failedOnly, setFailedOnly] = useState(false);
  const [selectedModel, setSelectedModel] = useState("");
  const [overview, setOverview] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [proxyCalls, setProxyCalls] = useState([]);
  const [templateCalls, setTemplateCalls] = useState([]);
  const [users, setUsers] = useState([]);
  const [counts, setCounts] = useState({ proxy: 0, template: 0, users: 0 });
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [runtimeLoading, setRuntimeLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [overviewError, setOverviewError] = useState(false);
  const [runtimeError, setRuntimeError] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const PRESETS = [
    { value: "7d", label: t("AiMonitoringPage.preset7d") },
    { value: "30d", label: t("AiMonitoringPage.preset30d") },
    { value: "90d", label: t("AiMonitoringPage.preset90d") },
  ];
  const DETAIL_TABS = [
    { key: "proxy", label: t("AiMonitoringPage.tabProxy"), icon: "swap_horiz", count: counts.proxy },
    { key: "template", label: t("AiMonitoringPage.tabTemplate"), icon: "auto_awesome", count: counts.template },
    { key: "users", label: t("AiMonitoringPage.tabUsers"), icon: "groups", count: counts.users },
  ];

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setOverviewLoading(true);
      setRuntimeLoading(true);
      setDetailLoading(true);
    }
    const range = presetToRange(preset);
    const shared = { ...range, limit: 100 };

    // The overview and runtime cards are independent of the detail tables.
    // Resolve each group separately so a slow/unreachable gateway does not
    // keep already available usage data behind the page-level loading state.
    const overviewRequest = AiMonitoringService.overview({
      ...range,
      bucket: presetToBucket(preset),
      compare: true,
    })
      .then((value) => {
        setOverview(value);
        setOverviewError(false);
      })
      .catch(() => {
        setOverviewError(true);
        if (!silent) toast.error(t("AiMonitoringPage.loadError"));
      })
      .finally(() => setOverviewLoading(false));

    const runtimeRequest = AiMonitoringService.runtime()
      .then((value) => {
        setRuntime(value);
        setRuntimeError(false);
      })
      .catch(() => {
        setRuntimeError(true);
      })
      .finally(() => setRuntimeLoading(false));

    const detailRequest = Promise.allSettled([
      AiMonitoringService.listProxyCalls(shared),
      AiMonitoringService.listTemplateCalls(shared),
      AiMonitoringService.listUsersUsage(shared),
    ]).then(([proxyResult, templateResult, usersResult]) => {
      if (proxyResult.status === "fulfilled") {
        setProxyCalls(proxyResult.value?.data ?? []);
        setCounts((current) => ({ ...current, proxy: proxyResult.value?.count ?? proxyResult.value?.data?.length ?? 0 }));
      }
      if (templateResult.status === "fulfilled") {
        setTemplateCalls(templateResult.value?.data ?? []);
        setCounts((current) => ({ ...current, template: templateResult.value?.count ?? templateResult.value?.data?.length ?? 0 }));
      }
      if (usersResult.status === "fulfilled") {
        setUsers(usersResult.value?.data ?? []);
        setCounts((current) => ({ ...current, users: usersResult.value?.count ?? usersResult.value?.data?.length ?? 0 }));
      }
    }).finally(() => {
      setDetailLoading(false);
    });

    await Promise.allSettled([overviewRequest, runtimeRequest, detailRequest]);
    setLastUpdated(new Date());
  }, [preset, t, toast]);

  useEffect(() => { load(); }, [load]);
  useAutoRefresh(() => load(true));

  const summary = overview?.summary;
  const comparison = overview?.comparison;
  const detailQuery = selectedModel || query;
  const detailPlaceholder = detailTab === "users"
    ? t("AiMonitoringPage.searchPlaceholderUsers")
    : t("AiMonitoringPage.searchPlaceholderCalls");

  const selectModel = (modelName) => {
    setSelectedModel(modelName);
    const hasProxyCalls = proxyCalls.some((call) => call.model_name === modelName);
    const hasTemplateCalls = templateCalls.some((call) => call.model_name === modelName);
    setDetailTab(hasProxyCalls || !hasTemplateCalls ? "proxy" : "template");
    setQuery("");
    setFailedOnly(false);
  };

  const detailStatusLabel = failedOnly
    ? t("AiMonitoringPage.failedOnly")
    : t("AiMonitoringPage.allRecords");

  return (
    <div className={styles.page}>
      <PageHeader title={t("AiMonitoringPage.pageTitle")} subtitle={t("AiMonitoringPage.pageSubtitle")}>
        <div className={styles.pageActions}>
          <div className={styles.refreshMeta}>
            <span className={styles.refreshDot} />
            <span>{lastUpdated ? t("AiMonitoringPage.lastUpdated", { time: lastUpdated.toLocaleTimeString("zh-TW") }) : t("AiMonitoringPage.waitingForData")}</span>
          </div>
          <div className={styles.segment} role="group" aria-label={t("AiMonitoringPage.rangeLabel")}>
            {PRESETS.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`${styles.segmentBtn} ${preset === item.value ? styles.segmentActive : ""}`}
                onClick={() => setPreset(item.value)}
                aria-pressed={preset === item.value}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </PageHeader>

      <StatusBanner overview={overview} runtime={runtime} overviewError={overviewError} runtimeError={runtimeError} t={t} />

      <section className={styles.metricRow} aria-label={t("AiMonitoringPage.summaryTitle")}>
        <MetricGroupCard
          icon="swap_calls"
          tone="primary"
          label={t("AiMonitoringPage.usageGroupTitle")}
          items={[
            {
              key: "calls",
              label: t("AiMonitoringPage.statCallCount"),
              value: summary ? formatNumber(summary.total_calls) : "—",
              detail: t("AiMonitoringPage.previousPeriod"),
              delta: comparison ? formatDelta(comparison.total_calls_percent) : null,
              deltaTone: comparison?.total_calls_percent > 0 ? "neutral" : "positive",
            },
            {
              key: "tokens",
              label: t("AiMonitoringPage.statTokensTotal"),
              value: formatTokens(summary?.total_tokens),
            },
          ]}
        />
        <MetricGroupCard
          icon="error_outline"
          tone="danger"
          label={t("AiMonitoringPage.reliabilityGroupTitle")}
          items={[
            {
              key: "failed-calls",
              label: t("AiMonitoringPage.statFailedCalls"),
              value: summary ? formatNumber(summary.failed_calls) : "—",
              detail: t("AiMonitoringPage.previousPeriod"),
              delta: comparison ? formatDelta(comparison.failed_calls_delta, "") : null,
              deltaTone: comparison?.failed_calls_delta > 0 ? "danger" : "positive",
            },
            {
              key: "error-rate",
              label: t("AiMonitoringPage.statErrorRate"),
              value: formatPercent(summary?.error_rate),
              detail: t("AiMonitoringPage.previousPeriod"),
              delta: comparison ? formatDelta(comparison.error_rate_delta, "pp") : null,
              deltaTone: comparison?.error_rate_delta > 0 ? "danger" : "positive",
            },
          ]}
        />
        <MetricCard
          icon="speed"
          tone="info"
          label={t("AiMonitoringPage.statAvgLatency")}
          value={formatDuration(summary?.avg_latency_ms)}
          detail={t("AiMonitoringPage.previousPeriod")}
          delta={comparison?.avg_latency_ms_delta != null ? formatDelta(comparison.avg_latency_ms_delta, "ms") : null}
          deltaTone={comparison?.avg_latency_ms_delta > 0 ? "danger" : "positive"}
        />
      </section>

      <section className={styles.primaryGrid}>
        <div className={`${styles.panel} ${styles.trendPanel}`}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}><MIcon name="timeline" size={18} />{t("AiMonitoringPage.trendTitle")}</h2>
              <p className={styles.panelDescription}>{t("AiMonitoringPage.trendDescription")}</p>
            </div>
            <div className={styles.trendMeta}>
              <span>{t("AiMonitoringPage.totalTokensShort", { value: formatTokens(summary?.total_tokens) })}</span>
              <span>{t("AiMonitoringPage.activeUsersShort", { value: formatNumber(summary?.active_users) })}</span>
            </div>
          </div>
          <TrendChart series={overview?.series} bucket={overview?.bucket ?? presetToBucket(preset)} loading={overviewLoading} t={t} />
        </div>
        <ModelStatusPanel runtime={runtime} error={runtimeError} loading={runtimeLoading} t={t} />
      </section>

      <section className={styles.secondaryGrid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}><MIcon name="model_training" size={18} />{t("AiMonitoringPage.modelBreakdownTitle")}</h2>
              <p className={styles.panelDescription}>{t("AiMonitoringPage.modelBreakdownDescription")}</p>
            </div>
            <span className={styles.columnHint}>{t("AiMonitoringPage.breakdownCallsHeader")} · {t("AiMonitoringPage.breakdownTokensHeader")} · {t("AiMonitoringPage.breakdownErrorHeader")}</span>
          </div>
          <ModelBreakdown models={overview?.model_breakdown} t={t} onModelSelect={selectModel} />
        </div>
        <div className={`${styles.panel} ${styles.healthNote}`}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}><MIcon name="insights" size={18} />{t("AiMonitoringPage.readingTitle")}</h2>
              <p className={styles.panelDescription}>{t("AiMonitoringPage.readingDescription")}</p>
            </div>
          </div>
          <div className={styles.readingRows}>
            <div><span>{t("AiMonitoringPage.successfulCalls")}</span><strong>{formatNumber(summary?.successful_calls)}</strong></div>
            <div><span>{t("AiMonitoringPage.totalTokens")}</span><strong>{formatTokens(summary?.total_tokens)}</strong></div>
            <div><span>{t("AiMonitoringPage.activeUsers")}</span><strong>{formatNumber(summary?.active_users)}</strong></div>
          </div>
        </div>
      </section>

      <section className={styles.detailSection} aria-labelledby="detail-heading">
        <div className={styles.detailHeader}>
          <div>
            <h2 id="detail-heading" className={styles.detailTitle}>{t("AiMonitoringPage.detailTitle")}</h2>
            <p className={styles.detailDescription}>{t("AiMonitoringPage.detailDescription")}</p>
          </div>
          <div className={styles.detailToolbar}>
            <div className={styles.search}>
              <MIcon name="search" size={16} />
              <input
                type="text"
                className={styles.searchInput}
                placeholder={detailPlaceholder}
                value={selectedModel ? selectedModel : query}
                onChange={(event) => { setSelectedModel(""); setQuery(event.target.value); }}
                aria-label={detailPlaceholder}
              />
              {(query || selectedModel) ? <button type="button" className={styles.clearSearch} onClick={() => { setQuery(""); setSelectedModel(""); }} aria-label={t("AiMonitoringPage.clearSearch")}><MIcon name="close" size={14} /></button> : null}
            </div>
            <button type="button" className={`${styles.filterButton} ${failedOnly ? styles.filterButtonActive : ""}`} onClick={() => setFailedOnly((current) => !current)} aria-pressed={failedOnly}>
              <MIcon name="filter_alt" size={15} />{detailStatusLabel}
            </button>
          </div>
        </div>
        <div className={styles.detailTabs} role="tablist" aria-label={t("AiMonitoringPage.detailTitle")}>
          {DETAIL_TABS.map((item) => (
            <button key={item.key} type="button" role="tab" aria-selected={detailTab === item.key} className={`${styles.detailTab} ${detailTab === item.key ? styles.detailTabActive : ""}`} onClick={() => { setDetailTab(item.key); setQuery(""); setSelectedModel(""); }}>
              <MIcon name={item.icon} size={16} />{item.label}<span className={styles.tabCount}>{formatNumber(item.count)}</span>
            </button>
          ))}
        </div>
        <div className={styles.detailContent}>
          {detailLoading ? <LoadingState /> : <DetailTable tab={detailTab} calls={{ proxy: proxyCalls, template: templateCalls }} users={users} query={detailQuery} failedOnly={failedOnly} t={t} />}
        </div>
      </section>
    </div>
  );
}
