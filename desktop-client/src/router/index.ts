import { createRouter, createWebHashHistory, RouteRecordRaw } from "vue-router";

const Layout = () => import("@/layout/index.vue");

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "Login",
    meta: { title: "router.login.title", hidden: true },
    component: () => import("@/views/login/index.vue")
  },
  {
    path: "/",
    name: "Index",
    component: Layout,
    redirect: "/home",
    children: [
      {
        path: "/home",
        name: "Home",
        meta: {
          title: "router.home.title",
          icon: "rocket-launch-rounded",
          keepAlive: false
        },
        component: () => import("@/views/home/index.vue")
      },
      {
        path: "/resources",
        name: "Resources",
        meta: {
          title: "router.resources.title",
          icon: "cloud",
          keepAlive: false
        },
        component: () => import("@/views/resources/index.vue")
      },
      {
        path: "/logger",
        name: "Logger",
        meta: {
          title: "router.logger.title",
          icon: "file-copy-sharp",
          keepAlive: false
        },
        component: () => import("@/views/logger/index.vue")
      },
      {
        path: "/config",
        name: "Config",
        meta: {
          title: "router.config.title",
          icon: "settings",
          keepAlive: false
        },
        component: () => import("@/views/config/index.vue")
      },
      {
        path: "/about",
        name: "About",
        meta: {
          title: "router.about.title",
          icon: "info-sharp",
          keepAlive: false
        },
        component: () => import("@/views/about/index.vue")
      }
    ]
  }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

export default router;
