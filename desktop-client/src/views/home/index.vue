<script lang="ts" setup>
import Breadcrumb from "@/layout/compoenets/Breadcrumb.vue";
import router from "@/router";
import { useAppStore } from "@/store/app";
import { on, removeRouterListeners, send } from "@/utils/ipcUtils";
import { useDebounceFn } from "@vueuse/core";
import { ElMessage } from "element-plus";
import { computed, defineComponent, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ipcRouters } from "../../../electron/core/IpcRouter";

defineComponent({ name: "Home" });

const { t } = useI18n();
const appStore = useAppStore();
const loading = ref(false);

const status = computed(() => {
  if (!appStore.tunnelStatus.running) return "stopped";
  if (appStore.tunnelStatus.connectionError) return "error";
  return "running";
});

const uptime = computed(() => {
  if (!appStore.tunnelStatus.running || appStore.tunnelStatus.lastStartTime <= 0) {
    return "";
  }
  const elapsed = Math.floor(
    (Date.now() - appStore.tunnelStatus.lastStartTime) / 1000
  );
  const h = Math.floor(elapsed / 3600);
  const m = Math.floor((elapsed % 3600) / 60);
  const s = elapsed % 60;
  return `${h}h ${m}m ${s}s`;
});

const now = ref(Date.now());
const tickTimer = ref<number | null>(null);

const handleToggle = useDebounceFn(() => {
  if (!appStore.loggedIn) {
    router.push({ name: "Login" });
    return;
  }
  loading.value = true;
  if (appStore.tunnelStatus.running) {
    send(ipcRouters.TUNNEL.stop);
  } else {
    send(ipcRouters.TUNNEL.start);
  }
}, 300);

const goLogin = () => router.push({ name: "Login" });

watch(
  () => appStore.tunnelStatus.running,
  () => {
    loading.value = false;
  }
);

onMounted(() => {
  on(ipcRouters.TUNNEL.start, () => {
    loading.value = false;
  });
  on(ipcRouters.TUNNEL.stop, () => {
    loading.value = false;
  });
  tickTimer.value = window.setInterval(() => {
    now.value = Date.now();
  }, 1000);
});

onUnmounted(() => {
  removeRouterListeners(ipcRouters.TUNNEL.start);
  removeRouterListeners(ipcRouters.TUNNEL.stop);
  if (tickTimer.value) clearInterval(tickTimer.value);
});

const goResources = () => router.push({ name: "Resources" });
const goLogs = () => router.push({ name: "Logger" });
const copy = async (value: string) => {
  try {
    await navigator.clipboard.writeText(value);
    ElMessage.success(t("common.copied"));
  } catch {
    ElMessage.error("copy failed");
  }
};

const openSsh = (port: number) => {
  send(ipcRouters.SYSTEM.openSsh, { port });
};
</script>

<template>
  <div class="main">
    <breadcrumb />
    <div class="app-container-breadcrumb">
      <div class="flex flex-col gap-4 p-6 w-full h-full bg-white rounded drop-shadow-lg overflow-auto">
        <div class="flex gap-8 items-center">
          <div
            class="flex relative justify-center items-center w-40 h-40 rounded-full border-4"
            :class="{
              'border-[#5A3DAA] text-[#5A3DAA]': status === 'running',
              'border-[#E6A23C] text-[#E6A23C]': status === 'error',
              'border-gray-300 text-gray-400': status === 'stopped'
            }"
          >
            <IconifyIconOffline class="text-6xl" icon="rocket-launch-rounded" />
          </div>

          <div class="flex flex-col flex-1 gap-3">
            <div class="text-xl font-bold">
              <span v-if="status === 'running'" class="text-[#5A3DAA]">
                {{ t("home.status.running") }}
              </span>
              <span v-else-if="status === 'error'" class="text-[#E6A23C]">
                {{ t("home.status.error") }}
              </span>
              <span v-else class="text-gray-500">
                {{ t("home.status.stopped") }}
              </span>
            </div>

            <div v-if="!appStore.loggedIn" class="text-sm text-amber-600">
              {{ t("home.empty.notLoggedIn") }}
            </div>
            <div v-else-if="status === 'running'" class="text-sm text-gray-500">
              {{ t("home.status.uptime", { time: uptime }) }}
            </div>
            <div v-else-if="status === 'error'" class="text-sm text-amber-600 break-all">
              {{ appStore.tunnelStatus.connectionError }}
            </div>

            <div class="flex gap-2">
              <el-button
                v-if="!appStore.loggedIn"
                type="primary"
                @click="goLogin"
              >
                {{ t("home.empty.goLogin") }}
              </el-button>
              <el-button
                v-else
                type="primary"
                :disabled="loading"
                @click="handleToggle"
              >
                {{
                  appStore.tunnelStatus.running
                    ? t("home.button.stop")
                    : t("home.button.start")
                }}
              </el-button>
              <el-button text @click="goLogs">{{ t("router.logger.title") }}</el-button>
            </div>
          </div>
        </div>

        <el-divider />

        <div>
          <h3 class="mb-2 text-base font-semibold">
            {{ t("home.tunnels.title") }}
          </h3>
          <div
            v-if="!appStore.tunnelStatus.tunnels.length"
            class="py-8 text-sm text-center text-gray-400"
          >
            <template v-if="!appStore.tunnelStatus.running">
              {{ t("home.tunnels.empty") }}
            </template>
            <template v-else>
              {{ t("home.empty.noTunnels") }}
            </template>
            <div class="mt-2">
              <el-link type="primary" @click="goResources">
                {{ t("home.empty.goResources") }}
              </el-link>
            </div>
          </div>
          <el-table
            v-else
            :data="appStore.tunnelStatus.tunnels"
            size="small"
            stripe
          >
            <el-table-column prop="vm_name" :label="t('resources.table.name')" />
            <el-table-column prop="vmid" :label="t('resources.table.vmid')" width="80" />
            <el-table-column prop="service" label="Service" width="100" />
            <el-table-column label="127.0.0.1:port" width="180">
              <template #default="{ row }">
                <span class="font-mono">127.0.0.1:{{ row.visitor_port }}</span>
                <el-button
                  class="ml-2"
                  size="small"
                  text
                  @click="copy(`127.0.0.1:${row.visitor_port}`)"
                >
                  {{ t("common.copy") }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column :label="t('home.tunnels.action')" width="110">
              <template #default="{ row }">
                <el-button
                  v-if="String(row.service).toLowerCase() === 'ssh'"
                  size="small"
                  type="primary"
                  @click="openSsh(row.visitor_port)"
                >
                  {{ t("home.tunnels.connectSsh") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>
