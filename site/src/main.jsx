import { createRoot, hydrateRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import LandingPage from "./landing/LandingPage";
import { createI18n } from "./i18n";
import { languageFromPath } from "./languages";
import "./site.scss";

/* 官網首頁＝原版介紹頁（像素版保留在 pixel.html，dev server 才看得到） */
const lang = languageFromPath(window.location.pathname);
const container = document.getElementById("root");
const app = (
  <I18nextProvider i18n={createI18n(lang)}>
    <LandingPage />
  </I18nextProvider>
);

// 正式建置的每個語言頁都是預渲染好的 HTML，直接接手；dev server 沒有預渲染，從頭畫
if (container.firstElementChild) {
  hydrateRoot(container, app);
} else {
  document.documentElement.lang = lang;
  createRoot(container).render(app);
}
