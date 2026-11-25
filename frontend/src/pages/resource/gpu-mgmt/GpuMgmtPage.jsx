import { Fragment, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import styles from "./GpuMgmtPage.module.scss";
import MIcon from "../../../components/MIcon";
import DataTable, { DataTableCells } from "../../../components/DataTable/DataTable";
import { baseFeatures } from "../../../components/DataTable/features";
import { useTableFitContext } from "../../../components/DataTable/TableFitContext";
import useTableFit from "../../../hooks/useTableFit";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import { GpuService } from "../../../services/gpu";
import { useGpuCacheUpdater, useGpuMappingsQuery } from "../../../queries/gpu";
import { useConfirm } from "../../../components/ConfirmDialog/ConfirmProvider";
import { useToast } from "../../../hooks/useToast";
import { useQueryView } from "../../../hooks/useQueryLoadState";
import LoadingState from "../../../components/LoadingState/LoadingState";
import PageHeader from "../../../components/PageHeader/PageHeader";

function useColumns() {
  const { t } = useTranslation("resource");
  return [
    t("GpuMgmtPage.columnMapping"),
    t("GpuMgmtPage.columnDescription"),
    t("GpuMgmtPage.columnNodePci"),
    t("GpuMgmtPage.columnAvailableTotal"),
    t("GpuMgmtPage.columnVmInUse"),
    t("GpuMgmtPage.columnStatus"),
    t("GpuMgmtPage.columnActions"),
  ];
}

/* 超過此數量的 PCI 位址改以「範圍摘要 + 展開列」顯示，避免 SR-IOV 撐爆列高 */
const PCI_COLLAPSE_THRESHOLD = 3;

/* 將 backend GPUMappingDetail 攤平為前端列 */
function flattenMappings(mappings) {
  return mappings.map((m) => {
    const mapEntries = (m.maps ?? []).map((entry, index) => ({
      key: `${entry.node ?? "node"}-${entry.path ?? "path"}-${entry.id ?? index}`,
      node: entry.node ?? "—",
      pci: entry.path ?? "—",
    }));
    const nodes = [
      ...new Set(mapEntries.map((entry) => entry.node).filter((node) => node !== "—")),
    ];
    const pciPaths = mapEntries.map((entry) => entry.pci).filter((path) => path !== "—");
    return {
      id: m.id,
      mapping: m.id,
      description: m.description,
      node: nodes.join(", ") || "—",
      pci: pciPaths.join(", ") || "—",
      mapEntries,
      device_count: m.device_count,
      capacity_count: m.capacity_count || m.device_count,
      used_count: m.used_count,
      available_count: m.available_count,
      total_vram_mb: m.total_vram_mb,
      used_vram_mb: m.used_vram_mb,
      used_vram_known: m.used_vram_known ?? true,
      per_instance_vram_mb: m.per_instance_vram_mb,
      mdev_profile: m.mdev_profile,
      is_sriov: m.is_sriov,
      vms: (m.used_by ?? []).map((u) => ({
        vmid: u.vmid,
        name: u.vm_name,
        status: u.status,
      })),
    };
  });
}

/* 解析 PCI 位址 domain:bus:device.function；function 佔 3 bits，
   以 device*8+function 當序數判斷 VF 是否連續（15:00.7 的下一個是 15:01.0） */
function parsePci(path) {
  const m = /^([0-9a-fA-F]{4}:[0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-9a-fA-F])$/.exec(path ?? "");
  if (!m) return null;
  return { prefix: m[1], ord: parseInt(m[2], 16) * 8 + parseInt(m[3], 16) };
}

/* 將同節點、同 domain:bus 的連續位址壓成區段；無法解析或不連續就各自成段 */
function compressEntries(mapEntries) {
  const segments = [];
  for (const entry of mapEntries) {
    const parsed = parsePci(entry.pci);
    const last = segments[segments.length - 1];
    if (
      parsed &&
      last?.endOrd != null &&
      last.node === entry.node &&
      last.prefix === parsed.prefix &&
      parsed.ord === last.endOrd + 1
    ) {
      last.end = entry.pci;
      last.endOrd = parsed.ord;
      last.count += 1;
    } else {
      segments.push({
        node: entry.node,
        start: entry.pci,
        end: entry.pci,
        prefix: parsed?.prefix,
        endOrd: parsed?.ord ?? null,
        count: 1,
      });
    }
  }
  return segments;
}

/* 區段顯示文字，迄端省略 domain：0000:15:00.2 – 15:03.7 */
function formatSegment(seg) {
  if (seg.count === 1) return seg.start;
  return `${seg.start} – ${seg.end.replace(/^[0-9a-fA-F]{4}:/, "")}`;
}

/* 依節點分組（保留原始順序），供展開列分節顯示 */
function groupByNode(mapEntries) {
  const groups = [];
  for (const entry of mapEntries) {
    const last = groups[groups.length - 1];
    if (last && last.node === entry.node) last.items.push(entry);
    else groups.push({ node: entry.node, items: [entry] });
  }
  return groups;
}

/* 每個節點有幾個位址（保留首次出現的順序），供收合摘要只列節點時用 */
function summarizeNodes(mapEntries) {
  const counts = new Map();
  for (const entry of mapEntries) counts.set(entry.node, (counts.get(entry.node) ?? 0) + 1);
  return [...counts].map(([node, count]) => ({ node, count }));
}

/* MB → 人類可讀（512 MB / 4 GB / 1.5 GB）。
   數字與單位之間用不換行空格：欄位變窄時 VRAM 那行會換行，不會拆成「12」「GB」兩行 */
function formatVram(mb) {
  if (!mb || mb <= 0) return "";
  if (mb < 1024) return `${mb} MB`;
  const gb = mb / 1024;
  return `${Number.isInteger(gb) ? gb : gb.toFixed(1)} GB`;
}

/* 有搜尋條件時（onClearSearch）是「沒有符合的」，不是「還沒偵測到 GPU」 */
function EmptyState({ onClearSearch }) {
  const { t } = useTranslation("resource");
  return <SharedEmptyState icon="memory" title={t(onClearSearch ? "GpuMgmtPage.emptyFilteredTitle" : "GpuMgmtPage.emptyTitle")}
    action={onClearSearch && <button type="button" className={styles.btnSecondary} onClick={onClearSearch}><MIcon name="search_off" size={16} />{t("EmptyState.clearSearch", { ns: "common" })}</button>} />;
}

function StatusBadge({ used, total }) {
  const { t } = useTranslation("resource");
  if (total === 0) {
    return <span className={`${styles.badge} ${styles.badge_unknown}`}>{t("GpuMgmtPage.statusUnknown")}</span>;
  }
  if (used === 0) {
    return <span className={`${styles.badge} ${styles.badge_available}`}>{t("GpuMgmtPage.statusAvailable")}</span>;
  }
  if (used >= total) {
    return <span className={`${styles.badge} ${styles.badge_full}`}>{t("GpuMgmtPage.statusFull")}</span>;
  }
  return (
    <span className={`${styles.badge} ${styles.badge_inuse}`}>
      {t("GpuMgmtPage.statusInUse", { used, total })}
    </span>
  );
}

function VmChips({ vms }) {
  const { t } = useTranslation("resource");
  if (!vms || vms.length === 0) {
    return <span className={styles.muted}>—</span>;
  }
  return (
    <div className={styles.vmChips}>
      {vms.map((vm) => (
        <span key={vm.vmid} className={styles.vmChip} title={t("GpuMgmtPage.vmidTitle", { vmid: vm.vmid })}>
          <MIcon name="computer" size={14} />
          <span>{vm.name || t("GpuMgmtPage.vmFallbackName", { vmid: vm.vmid })}</span>
          <span
            className={`${styles.dot} ${vm.status === "running" ? styles.dotRunning : styles.dotStopped}`}
          />
        </span>
      ))}
    </div>
  );
}

/* ── 表格欄位（TanStack Table）──
   v9 的 header／cell 會被當元件掛載，欄位定義放模組層級才不會每次 render 整格重新掛載。
   展開與刪除中的狀態由頁面管，經 GpuMappingRow 的 rowState 交給各欄 */
const columnHelper = createColumnHelper();

/* 欄名來自 useColumns() */
function ColumnTitle({ index }) {
  return useColumns()[index];
}

/* ── 窄版收欄（useTableFit，樣式規範「表格」規則四） ──
   表格區不夠寬時依序收起描述、節點 / PCI、可用 / 總數、使用中 VM；Mapping、狀態、操作永遠在。
   收起的內容改畫在名稱欄（描述、節點 / PCI：這張卡是什麼、裝在哪裡）與狀態欄（可用量、哪些 VM 在用）。
   欄寬只寫在這裡：節點 / PCI 一筆是節點名＋「0000:41:00.0」，要 200px；
   可用 / 總數底下的 VRAM 行（VRAM 使用中 12 GB / 48 GB）要 180px；英文的 Actions 表頭要 80px。
   全部欄 1150px：1440 寬（表格區約 1003px）只收描述、1366 筆電（約 929～944px）再收節點 / PCI，
   1100 寬視窗（約 678px）再收可用 / 總數；收到只剩三欄 440px，1440 開著 AI 助手（約 567px）、
   手機（約 448px）都還放得下 */
const GPU_FIT_COLUMNS = Object.freeze([
  { id: "mapping", width: 210 },
  { id: "description", width: 160, fold: 1 },
  { id: "pci", width: 200, fold: 2 },
  { id: "capacity", width: 180, fold: 3 },
  { id: "usage", width: 170, fold: 4 },
  { id: "status", width: 150 },
  { id: "actions", width: 80 },
]);

/* 窄版收欄時名稱欄多畫：描述（型號）一行、節點 / PCI 整塊（位址多時的展開鈕照樣能按） */
function GpuNameCell({ item, rowState }) {
  const { t } = useTranslation("resource");
  const fit = useTableFitContext();
  return (
    <div className={styles.nameCell}>
      <div className={styles.nameIcon}>
        <MIcon name="memory" size={18} />
      </div>
      <div className={styles.nameText}>
        <div className={styles.namePrimary}>{item.mapping}</div>
        <div className={styles.nameSub}>
          {item.is_sriov ? t("GpuMgmtPage.typeSriov") : t("GpuMgmtPage.typePassthrough")}
          {item.mdev_profile ? ` · ${item.mdev_profile}` : ""}
          {item.per_instance_vram_mb > 0
            ? t("GpuMgmtPage.perInstanceVram", { vram: formatVram(item.per_instance_vram_mb) })
            : ""}
        </div>
        {fit.isFolded("description") && item.description && (
          <div className={styles.foldedLine}>{item.description}</div>
        )}
        {fit.isFolded("pci") && item.mapEntries.length > 0 && (
          <div className={styles.foldedBlock} data-guide="gpu-mgmt-pci">
            <GpuPciCell item={item} rowState={rowState} />
          </div>
        )}
      </div>
    </div>
  );
}

/* rowState 由 GpuMappingRow 給：位址多時收合（collapsible）、目前是否展開、VF／裝置的單位、展開鈕 */
function GpuPciCell({ item, rowState }) {
  const { collapsible, expanded, unitLabel, onToggleExpanded } = rowState;
  if (item.mapEntries.length === 0) return <span className={styles.muted}>—</span>;
  if (collapsible) {
    /* 位址不連續時壓不成區段（整張卡直通的 8 張卡就是 8 段），摘要只留節點，
       位址交給展開列；多個節點時各自帶數量 */
    const segments = compressEntries(item.mapEntries);
    const nodeCounts = summarizeNodes(item.mapEntries);
    return (
      <div className={styles.mapSummary}>
        {segments.length <= PCI_COLLAPSE_THRESHOLD
          ? segments.map((seg) => (
              <span key={`${seg.node}-${seg.start}`} className={styles.mapEntry}>
                <span className={styles.mapNode}>{seg.node}</span>
                <code className={styles.code}>{formatSegment(seg)}</code>
              </span>
            ))
          : nodeCounts.map(({ node, count }) => (
              <span key={node} className={styles.mapNodeOnly}>
                {nodeCounts.length > 1 ? `${node} × ${count}` : node}
              </span>
            ))}
        <button
          type="button"
          className={`${styles.vfChip} ${expanded ? styles.vfChipOpen : ""}`}
          aria-expanded={expanded}
          onClick={onToggleExpanded}
        >
          {item.mapEntries.length} {unitLabel}
          <MIcon name="expand_more" size={14} />
        </button>
      </div>
    );
  }
  return (
    <div className={styles.mapList}>
      {item.mapEntries.map((entry) => (
        <div key={entry.key} className={styles.mapEntry}>
          <span className={styles.mapNode}>{entry.node}</span>
          <code className={styles.code}>{entry.pci}</code>
        </div>
      ))}
    </div>
  );
}

/* folded：收進狀態欄時，可用數改成帶欄名的小字行——狀態徽章已寫「2/4 使用中」，
   光寫「2 / 4」分不出是可用還是已用；數字整段一起換行，不拆成「2 /」「4」 */
function GpuCapacityCell({ item, folded = false }) {
  const { t } = useTranslation("resource");
  const count = `${item.available_count} / ${item.capacity_count}`;
  return (
    <>
      {folded ? (
        <div className={styles.foldedLine}>
          {t("GpuMgmtPage.columnAvailableTotal")} <span className={styles.foldedValue}>{count}</span>
        </div>
      ) : (
        <div>{count}</div>
      )}
      {item.is_sriov && item.capacity_count !== item.device_count && (
        <div className={styles.cellSub}>{item.device_count} VF</div>
      )}
      {item.total_vram_mb > 0 && (
        <div className={styles.cellSub}>
          {item.used_vram_known
            ? t("GpuMgmtPage.vramInUse", { used: formatVram(item.used_vram_mb) || "0", total: formatVram(item.total_vram_mb) })
            : t("GpuMgmtPage.vramUnknown", { total: formatVram(item.total_vram_mb) })}
        </div>
      )}
    </>
  );
}

/* 窄版收欄時狀態欄多畫：可用 / 總數（含 VF、VRAM），再來是哪些 VM 在用（沒有就不放）。
   導覽錨點跟著內容搬過來，收欄後導覽照樣指得到 */
function GpuStatusCell({ item }) {
  const fit = useTableFitContext();
  return (
    <>
      <StatusBadge used={item.used_count} total={item.capacity_count} />
      {fit.isFolded("capacity") && (
        <div className={styles.foldedBlock} data-guide="gpu-mgmt-capacity">
          <GpuCapacityCell item={item} folded />
        </div>
      )}
      {fit.isFolded("usage") && item.vms.length > 0 && (
        <div className={styles.foldedBlock} data-guide="gpu-mgmt-usage">
          <VmChips vms={item.vms} />
        </div>
      )}
    </>
  );
}

function GpuDeleteCell({ item, deleting, onDelete }) {
  const { t } = useTranslation("resource");
  return (
    <div className={styles.actions}>
      <button
        type="button"
        className={styles.actionBtnDanger}
        title={t("GpuMgmtPage.removeMappingTitle")}
        aria-label={`${t("GpuMgmtPage.removeMappingTitle")} ${item.mapping}`}
        disabled={deleting}
        onClick={onDelete}
      >
        <MIcon name="delete" size={16} />
      </button>
    </div>
  );
}

/* 導覽錨點用字面值寫在各欄（"data-guide": "…"），pageGuides 測試與改 UI 時的搜尋才找得到 */
const tdMeta = (tdProps) => ({
  thClassName: styles.th,
  tdClassName: styles.td,
  ...(tdProps ? { tdProps } : {}),
});

const gpuColumns = columnHelper.columns([
  columnHelper.accessor("mapping", {
    header: () => <ColumnTitle index={0} />,
    cell: ({ row, rowState }) => <GpuNameCell item={row.original} rowState={rowState} />,
    meta: tdMeta(),
  }),
  columnHelper.accessor("description", {
    header: () => <ColumnTitle index={1} />,
    cell: ({ row }) => row.original.description || "—",
    meta: tdMeta(),
  }),
  columnHelper.display({
    id: "pci",
    header: () => <ColumnTitle index={2} />,
    cell: ({ row, rowState }) => <GpuPciCell item={row.original} rowState={rowState} />,
    meta: tdMeta({ "data-guide": "gpu-mgmt-pci" }),
  }),
  columnHelper.display({
    id: "capacity",
    header: () => <ColumnTitle index={3} />,
    cell: ({ row }) => <GpuCapacityCell item={row.original} />,
    meta: tdMeta({ "data-guide": "gpu-mgmt-capacity" }),
  }),
  columnHelper.display({
    id: "usage",
    header: () => <ColumnTitle index={4} />,
    cell: ({ row }) => <VmChips vms={row.original.vms} />,
    meta: tdMeta({ "data-guide": "gpu-mgmt-usage" }),
  }),
  columnHelper.display({
    id: "status",
    header: () => <ColumnTitle index={5} />,
    cell: ({ row }) => <GpuStatusCell item={row.original} />,
    meta: tdMeta(),
  }),
  columnHelper.display({
    id: "actions",
    header: () => <ColumnTitle index={6} />,
    cell: ({ row, rowState }) => <GpuDeleteCell item={row.original} deleting={rowState.deleting} onDelete={rowState.onDelete} />,
    meta: tdMeta({ "data-guide": "gpu-mgmt-delete" }),
  }),
]);

/* 一個對應一列；PCI 位址多的可以展開，下面多一列列出全部位址。
   inExpandedSet：頁面記著這筆展開了（位址不多的列沒有展開這回事）。
   展開列橫跨目前顯示中的欄（窄版收起的欄不畫，colSpan 跟著少） */
function GpuMappingRow({ row, item, inExpandedSet, deleting, onToggleExpanded, onDelete }) {
  const { t } = useTranslation("resource");
  const fit = useTableFitContext();
  const shownColumnCount = row.getAllCells().filter((cell) => !fit.isFolded(cell.column.id)).length;
  const collapsible = item.mapEntries.length > PCI_COLLAPSE_THRESHOLD;
  const expanded = collapsible && inExpandedSet;
  const unitLabel = item.is_sriov ? t("GpuMgmtPage.unitVf") : t("GpuMgmtPage.unitDevice");
  return (
    <Fragment>
      <tr className={`${styles.tr} ${expanded ? styles.trExpanded : ""}`}>
        <DataTableCells
          row={row}
          rowState={{
            collapsible,
            expanded,
            unitLabel,
            onToggleExpanded: () => onToggleExpanded(item.id),
            deleting,
            onDelete: () => onDelete(item.id),
          }}
        />
      </tr>

      {expanded && (
        <tr className={styles.detailTr}>
          <td className={styles.detailTd} colSpan={shownColumnCount}>
            <div className={styles.detailBody}>
              {groupByNode(item.mapEntries).map((group) => (
                <div key={group.node}>
                  <div className={styles.detailNode}>
                    {group.node} · {group.items.length} {unitLabel}
                  </div>
                  <div className={styles.pciGrid}>
                    {group.items.map((entry) => (
                      <code key={entry.key} className={styles.code}>{entry.pci}</code>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export default function GpuMgmtPage() {
  const { t } = useTranslation("resource");
  const toast = useToast();
  const confirm = useConfirm();
  const [filter, setFilter] = useState("");
  /* GPU 對應清單走 TanStack Query：背景 30 秒刷新、分頁隱藏時暫停；
     首次載不到才提示，背景刷新失敗沿用上一份（與原本靜默刷新相同） */
  const mappingsQuery = useGpuMappingsQuery();
  const gpuCache = useGpuCacheUpdater();
  const mappingsData = mappingsQuery.data;
  const rows = useMemo(() => flattenMappings(mappingsData?.data ?? []), [mappingsData]);
  /* 只有第一次載入時顯示載入畫面；首載失敗後顯示空清單（與原本相同），輪詢重試時不閃回載入畫面。
     沒資料時 v5 每次重抓都把 status 改回 pending、清掉 error，所以用 useQueryView（重試期間仍算失敗） */
  const mappingsView = useQueryView(mappingsQuery);
  const loading = mappingsView.loading;
  /* 依訊息字串觸發：還沒有資料時輪詢重試又失敗，訊息相同就不重複提示 */
  const loadFailedMessage = mappingsView.error
    ? mappingsView.error?.message ?? t("Error.generic", { ns: "common" })
    : null;
  useEffect(() => {
    if (loadFailedMessage) toast.error(loadFailedMessage);
  }, [loadFailedMessage, toast]);
  /* 刪除進行中：擋住重複點擊，等重新載入完成才解除 */
  const [deleting, setDeleting] = useState(false);
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  const toggleExpanded = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDelete = async (id) => {
    if (deleting) return;
    const ok = await confirm({
      title: t("GpuMgmtPage.deleteMappingTitle"),
      message: t("GpuMgmtPage.deleteMappingMessage", { id }),
      confirmText: t("GpuMgmtPage.deleteConfirm"),
      danger: true,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await GpuService.deleteMapping(id);
      toast.success(t("GpuMgmtPage.deletedToast"));
      /* 等清單重新載入完才解鎖，避免使用者對已刪掉的舊列再按一次（重抓失敗沿用舊清單、不提示） */
      await gpuCache.invalidate();
    } catch (e) {
      toast.error(e?.message ?? t("GpuMgmtPage.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (n) =>
        (n.mapping ?? "").toLowerCase().includes(q) ||
        (n.description ?? "").toLowerCase().includes(q) ||
        (n.node ?? "").toLowerCase().includes(q) ||
        (n.pci ?? "").toLowerCase().includes(q) ||
        n.mapEntries.some(
          (entry) =>
            entry.node.toLowerCase().includes(q) ||
            entry.pci.toLowerCase().includes(q),
        ),
    );
  }, [rows, filter]);

  const table = useTable({
    features: baseFeatures,
    columns: gpuColumns,
    data: visible,
    getRowId: (item) => String(item.id),
  });
  const fit = useTableFit(GPU_FIT_COLUMNS);

  return (
    <div className={styles.page}>
      <PageHeader title={t("GpuMgmtPage.pageTitle")} />

      <div className={styles.toolbar}>
        <div className={styles.search} data-guide="gpu-mgmt-search">
          <MIcon name="search" size={16} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder={t("GpuMgmtPage.searchPlaceholder")}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>

      <div className={styles.content}>
        {loading ? (
          <LoadingState fullPage />
        ) : visible.length === 0 ? (
          <EmptyState onClearSearch={filter.trim() ? () => setFilter("") : undefined} />
        ) : (
          <div ref={fit.ref} className={styles.tableWrap} data-guide="gpu-mgmt-table">
            <DataTable
              table={table}
              fit={fit}
              className={styles.table}
              renderRow={(row) => (
                <GpuMappingRow
                  key={row.id}
                  row={row}
                  item={row.original}
                  inExpandedSet={expandedIds.has(row.original.id)}
                  deleting={deleting}
                  onToggleExpanded={toggleExpanded}
                  onDelete={handleDelete}
                />
              )}
            />
          </div>
        )}
      </div>
    </div>
  );
}
