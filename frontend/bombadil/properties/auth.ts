/**
 * 權限邊界性質（S 系列，見計畫 §5）：學生、老師在畫面上走不進不該進的頁面。
 */
import { always } from "@antithesishq/bombadil";
import { extract } from "@antithesishq/bombadil/browser";
import { ADMIN_ONLY, TEACH_ONLY, notFound, route } from "../lib/navigation.ts";

/** 頁面上所有站內連結的路徑 */
const linkPaths = extract((s) =>
  Array.from(s.document.querySelectorAll("a[href]"))
    .map((a) => a.getAttribute("href") ?? "")
    .filter((h) => h.startsWith("/")),
);

const onAdminRoute = () => ADMIN_ONLY.test(route.current);
const onTeachRoute = () => TEACH_ONLY.test(route.current);

/**
 * 頁面標題（PageHeader 的 h1）；404 頁只有 h2。
 * 只看 DashboardLayout 的主區（側欄 aside 後面的 main）：登入預檢頁不分網址蓋在任何路由上，
 * 它的 h1「準備完成，出發！」不是路由頁面的內容（校準實測在登入後約 3 秒誤報）。
 */
const pageTitle = extract((s) => s.document.querySelector("aside ~ main h1")?.textContent?.trim() ?? "");

/**
 * S1：非管理員停在管理員路由時，畫面上不會有任何頁面標題（只會是 404）。
 * 不用「5 秒內出現 404」的寫法：探索很快就離開該頁，eventually 會因為離開而成立，抓不到（P5 實測）。
 */
export const adminRoutesShowNotFound = always(() => !(onAdminRoute() && pageTitle.current !== "" && !notFound.current));

/** S2：學生進到教學路由會立刻被導走：停在教學路由時畫面上不會有頁面標題（理由同 S1） */
export const teachRoutesRedirectStudent = always(() => !(onTeachRoute() && pageTitle.current !== ""));

/** S3：非管理員的畫面上不出現管理員路由的連結 */
export const noAdminLinks = always(() => !linkPaths.current.some((p) => ADMIN_ONLY.test(p.split("?")[0])));

/** S4：學生的畫面上不出現教學路由的連結 */
export const noTeachLinks = always(() => !linkPaths.current.some((p) => TEACH_ONLY.test(p.split("?")[0])));
