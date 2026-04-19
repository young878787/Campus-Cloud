<script lang="ts">
import { ElConfigProvider } from "element-plus";
import en from "element-plus/dist/locale/en.mjs";
import zhCn from "element-plus/dist/locale/zh-cn.mjs";
import { defineComponent } from "vue";
import { useAppStore } from "./store/app";

export default defineComponent({
  name: "App",
  components: {
    [ElConfigProvider.name]: ElConfigProvider
  },
  computed: {
    currentLocale() {
      return useAppStore().language === "zh-CN" ? zhCn : en;
    }
  }
});
</script>

<template>
  <el-config-provider :locale="currentLocale">
    <router-view />
  </el-config-provider>
</template>
