/**
 * 官網像素版的 i18n：沿用原版的 landing 文案（標題、聯繫方式、影片說明），
 * 小遊戲的新文案放在 pixel namespace。日文版缺的條目會逐條退回英文。
 */
import i18next from "i18next";
import { languageInfo } from "../languages";
import landingZhTW from "../locales/zh-TW.json";
import landingEn from "../locales/en.json";
import landingJa from "../locales/ja.json";
import pixelZhTW from "./locales/zh-TW.json";
import pixelEn from "./locales/en.json";
import pixelJa from "./locales/ja.json";

const RESOURCES = {
  "zh-TW": { landing: landingZhTW, pixel: pixelZhTW },
  en: { landing: landingEn, pixel: pixelEn },
  ja: { landing: landingJa, pixel: pixelJa },
};

export function createPixelI18n(lang) {
  languageInfo(lang);
  const instance = i18next.createInstance();
  instance.init({
    resources: RESOURCES,
    lng: lang,
    fallbackLng: { ja: ["en"], default: ["zh-TW"] },
    ns: ["pixel", "landing"],
    defaultNS: "pixel",
    interpolation: { escapeValue: false },
    returnEmptyString: false,
    initAsync: false,
    react: { useSuspense: false },
  });
  return instance;
}
