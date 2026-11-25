import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { LANGUAGES } from "../languages";
import { createPixelI18n } from "./i18n";
import PixelLandingPage from "./PixelLandingPage";
import "../site.scss";

/*
 * 像素版首頁的預覽（首頁目前是原版介紹頁）：只在 dev server 的 pixel.html 看得到，不進正式建置。
 * 語言用 ?lang=en／ja 切換；頁面上的語言按鈕會連到正式的各語言首頁（原版）。
 */
const requested = new URLSearchParams(window.location.search).get("lang");
const lang = LANGUAGES.some((l) => l.code === requested) ? requested : "zh-TW";
document.documentElement.lang = lang;

createRoot(document.getElementById("root")).render(
  <I18nextProvider i18n={createPixelI18n(lang)}>
    <PixelLandingPage lang={lang} />
  </I18nextProvider>,
);
