import { describe, expect, test } from "vitest";
import {
  formatDuration,
  formatModelDisplay,
  formatTokens,
  isOkStatus,
  presetToBucket,
} from "./AiMonitoringPage";

describe("AiMonitoringPage formatting", () => {
  test("長區間使用日 bucket，短區間使用小時 bucket", () => {
    expect(presetToBucket("7d")).toBe("hour");
    expect(presetToBucket("30d")).toBe("day");
    expect(presetToBucket("90d")).toBe("day");
  });

  test("監控數字以可讀單位呈現", () => {
    expect(formatTokens(1200)).toBe("1.2K");
    expect(formatTokens(1200000)).toBe("1.2M");
    expect(formatDuration(1200)).toBe("1.2s");
    expect(formatDuration(null)).toBe("—");
  });

  test("模型名稱保留公開可辨識部分", () => {
    expect(formatModelDisplay("models--Qwen--Qwen2.5-7B")).toBe("Qwen/Qwen2.5-7B");
    expect(formatModelDisplay("/home/hmr0836/models/gemma4-26b-a4b-it-fp8")).toBe("gemma4-26b-a4b-it-fp8");
    expect(formatModelDisplay("public-model")).toBe("public-model");
  });

  test("呼叫狀態只把明確成功值視為成功", () => {
    expect(isOkStatus("success")).toBe(true);
    expect(isOkStatus(200)).toBe(true);
    expect(isOkStatus("upstream_http_503")).toBe(false);
  });
});
