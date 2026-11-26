/**
 * 權限邊界性質（S 系列，見計畫 §5）：學生、老師在畫面上走不進不該進的頁面。
 */
import { always, eventually, now } from "@antithesishq/bombadil";
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

/** S1：非管理員進到管理員路由，5 秒內只會看到 404（不會渲染管理頁） */
export const adminRoutesShowNotFound = always(
  now(onAdminRoute).implies(eventually(() => notFound.current || !onAdminRoute()).within(5, "seconds")),
);

/** S2：學生進到教學路由，5 秒內會被導走 */
export const teachRoutesRedirectStudent = always(
  now(onTeachRoute).implies(eventually(() => !onTeachRoute()).within(5, "seconds")),
);

/** S3：非管理員的畫面上不出現管理員路由的連結 */
export const noAdminLinks = always(() => !linkPaths.current.some((p) => ADMIN_ONLY.test(p.split("?")[0])));

/** S4：學生的畫面上不出現教學路由的連結 */
export const noTeachLinks = always(() => !linkPaths.current.some((p) => TEACH_ONLY.test(p.split("?")[0])));
