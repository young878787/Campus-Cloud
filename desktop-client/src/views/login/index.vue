<script lang="ts" setup>
import router from "@/router";
import { useAppStore } from "@/store/app";
import { on, removeRouterListeners, send } from "@/utils/ipcUtils";
import { ElMessage } from "element-plus";
import { ipcRenderer } from "electron";
import { defineComponent, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ipcRouters } from "../../../electron/core/IpcRouter";

defineComponent({ name: "Login" });

const { t } = useI18n();
const appStore = useAppStore();
const waiting = ref(false);

const handleLogin = () => {
  waiting.value = true;
  send(ipcRouters.AUTH.startLogin);
};

const handleCancel = () => {
  send(ipcRouters.AUTH.logout);
  waiting.value = false;
};

const authEventHandler = (_event: any, args: ApiResponse<any>) => {
  if (!args || args.bizCode !== "A1000") return;
  const payload = args.data;
  if (!payload) return;
  waiting.value = false;
  if (payload.type === "login-success") {
    ElMessage.success(t("login.success"));
    appStore.loggedIn = true;
    appStore.refreshAuth();
    router.replace({ name: "Home" });
  } else if (payload.type === "login-failure") {
    ElMessage.error(
      t("login.failure", { error: payload.error || "unknown" })
    );
  }
};

onMounted(() => {
  on(ipcRouters.AUTH.startLogin, () => {
    waiting.value = true;
  });
  ipcRenderer.on("auth:event", authEventHandler);
});

onUnmounted(() => {
  removeRouterListeners(ipcRouters.AUTH.startLogin);
  ipcRenderer.removeListener("auth:event", authEventHandler);
});
</script>

<template>
  <div
    class="flex flex-col justify-center items-center w-full h-screen bg-gradient-to-br from-slate-50 to-slate-200"
  >
    <div class="flex flex-col items-center p-10 max-w-md bg-white rounded-2xl shadow-xl">
      <img src="/logo/only/128x128.png" class="mb-4 w-20 h-20" alt="Logo" />
      <h1 class="mb-2 text-2xl font-bold">{{ t("login.title") }}</h1>
      <p class="mb-6 text-sm text-center text-gray-500">
        {{ t("login.description") }}
      </p>
      <el-button
        v-if="!waiting"
        type="primary"
        size="large"
        class="w-full"
        @click="handleLogin"
      >
        {{ t("login.startButton") }}
      </el-button>
      <template v-else>
        <el-button size="large" class="mb-2 w-full" loading>
          {{ t("login.waiting") }}
        </el-button>
        <el-button size="small" text @click="handleCancel">
          {{ t("login.cancelButton") }}
        </el-button>
      </template>
    </div>
  </div>
</template>
