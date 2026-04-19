<script lang="ts" setup>
import Breadcrumb from "@/layout/compoenets/Breadcrumb.vue";
import { send } from "@/utils/ipcUtils";
import { defineComponent } from "vue";
import { useI18n } from "vue-i18n";
import { ipcRouters } from "../../../electron/core/IpcRouter";
import pkg from "../../../package.json";

defineComponent({ name: "About" });

const { t } = useI18n();

const openAppData = () => send(ipcRouters.SYSTEM.openAppData);
</script>

<template>
  <div class="main">
    <breadcrumb />
    <div class="app-container-breadcrumb">
      <div
        class="flex flex-col gap-6 justify-center items-center p-8 w-full h-full bg-white rounded drop-shadow-lg"
      >
        <img src="/logo/only/128x128.png" class="w-24 h-24" alt="Logo" />
        <div class="text-xl font-bold">{{ t("about.name") }}</div>
        <div class="max-w-md text-sm text-center text-gray-500">
          {{ t("about.description") }}
        </div>
        <div class="flex gap-3">
          <el-tag size="small" type="success">{{ t("about.features.oneClick") }}</el-tag>
          <el-tag size="small" type="primary">{{ t("about.features.bundled") }}</el-tag>
          <el-tag size="small" type="warning">{{ t("about.features.secure") }}</el-tag>
        </div>
        <div class="text-xs text-gray-400">
          {{ t("about.version") }} v{{ pkg.version }}
        </div>
        <el-button size="small" @click="openAppData">
          {{ t("about.openDataDir") }}
        </el-button>
      </div>
    </div>
  </div>
</template>
