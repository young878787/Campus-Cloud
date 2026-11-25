/* 預渲染實際跑在 Node 上、載入真的 gsap:這裡不 mock,確保 build 時的 SSR 能畫出每個語言 */
import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";
import { LANGUAGES, render } from "./entry-server";
import { CONTACT_EMAIL } from "./config";
import { LANGUAGE_STORAGE_KEY } from "./languagePreference";
import { DEMOS } from "./landing/LandingPage";
import zhTW from "./locales/zh-TW.json";
import en from "./locales/en.json";
import ja from "./locales/ja.json";

/* 首頁是原版介紹頁：除了聯繫方式，也確認畫出來的不是像素版（像素版才有「功能一覽」） */
describe.each([
  ["zh-TW", "SkyLab — 校園的高效雲端教學與實作基地", "聯繫我們", "功能一覽"],
  ["en", "SkyLab — An efficient campus cloud for teaching and labs", "Contact us", "Features at a glance"],
  ["ja", "SkyLab — キャンパスの高効率なクラウド教育・実習基盤", "お問い合わせ", "機能一覧"],
])("render(%s)", (lang, title, contact, specs) => {
  test("頁面內容與 SEO 標籤都是該語言", () => {
    const { html, head } = render(lang);
    expect(head).toContain(`<title>${title}</title>`);
    expect(html).toContain(contact);
    expect(html).not.toContain(specs);
    expect(html).toContain(CONTACT_EMAIL);
  });
});

test("只有根網址(預設語言)帶依瀏覽器語言轉頁的腳本", () => {
  expect(render("zh-TW").head).toContain(`<script>(function(){`);
  expect(render("zh-TW").head).toContain(LANGUAGE_STORAGE_KEY);
  expect(render("en").head).not.toContain(LANGUAGE_STORAGE_KEY);
  expect(render("ja").head).not.toContain(LANGUAGE_STORAGE_KEY);
});

test("三個語言都有預渲染,分享縮圖也都在 public/", () => {
  expect(LANGUAGES.map((l) => l.code)).toEqual(["zh-TW", "en", "ja"]);
  for (const { ogImage } of LANGUAGES) {
    expect(existsSync(path.join(import.meta.dirname, "..", "public", ogImage)), ogImage).toBe(true);
  }
});

/* 影片由 website/scripts/manual-shots/clips.mjs 錄製;少一支,展示區就會停在空白的框 */
test("實際操作影片與封面圖兩種語言都在 public/demo/", () => {
  for (const dir of ["en", "zh-TW"]) {
    for (const { id } of DEMOS) {
      for (const ext of ["mp4", "jpg"]) {
        const file = path.join(import.meta.dirname, "..", "public", "demo", dir, `${id}.${ext}`);
        expect(existsSync(file), `${dir}/${id}.${ext}`).toBe(true);
      }
    }
  }
});

/* 三語要一起改:任何一個語言少了 key,畫面就會露出 key 名稱 */
test("三個語系檔的 key 完全一致", () => {
  const keys = (obj, prefix = "") =>
    Object.entries(obj).flatMap(([k, v]) =>
      v && typeof v === "object" && !Array.isArray(v) ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
    );
  expect(keys(en).sort()).toEqual(keys(zhTW).sort());
  expect(keys(ja).sort()).toEqual(keys(zhTW).sort());
});
