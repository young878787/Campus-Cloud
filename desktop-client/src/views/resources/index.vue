<script lang="ts" setup>
import Breadcrumb from "@/layout/compoenets/Breadcrumb.vue";
import { useAppStore } from "@/store/app";
import { defineComponent, onMounted } from "vue";
import { useI18n } from "vue-i18n";

defineComponent({ name: "Resources" });

const { t } = useI18n();
const appStore = useAppStore();

const refresh = () => {
  if (appStore.loggedIn) appStore.refreshResources();
};

onMounted(() => {
  refresh();
});

const statusTagType = (status: string) => {
  if (status === "running") return "success";
  if (status === "stopped") return "info";
  return "warning";
};
</script>

<template>
  <div class="main">
    <breadcrumb />
    <div class="app-container-breadcrumb">
      <div class="flex flex-col gap-3 p-4 w-full h-full bg-white rounded drop-shadow-lg overflow-auto">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold">{{ t("resources.title") }}</h2>
          <el-button size="small" type="primary" @click="refresh">
            {{ t("resources.refresh") }}
          </el-button>
        </div>

        <el-table
          v-if="appStore.resources.length"
          :data="appStore.resources"
          size="small"
          stripe
        >
          <el-table-column prop="name" :label="t('resources.table.name')" />
          <el-table-column prop="vmid" :label="t('resources.table.vmid')" width="80" />
          <el-table-column prop="type" :label="t('resources.table.type')" width="90" />
          <el-table-column :label="t('resources.table.status')" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="node" :label="t('resources.table.node')" width="100" />
          <el-table-column prop="ip_address" :label="t('resources.table.ip')" />
          <el-table-column
            prop="environment_type"
            :label="t('resources.table.environment')"
            width="110"
          />
        </el-table>

        <div v-else class="py-12 text-sm text-center text-gray-400">
          {{ t("resources.empty") }}
        </div>
      </div>
    </div>
  </div>
</template>
