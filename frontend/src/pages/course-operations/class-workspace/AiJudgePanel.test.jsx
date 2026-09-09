import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import {
  ChatPanel,
  CreateCheckChooser,
  RubricTable,
  ScriptGenerationNotice,
  SessionTitle,
  buildProposalDiff,
  getRubricDisplayName,
  getRubricCheckTitle,
  getRubricItemsValue,
  getRubricReviewItemIds,
  getPendingRubricItemIds,
  getScriptCreationBlocker,
  getSessionMenuPosition,
  getSelectedRubricSource,
  getScriptCreationDestination,
  resolveActiveSessionId,
} from "./AiJudgePanel";
import { RUBRIC_POLISH_PROMPT } from "../../../services/aiJudge";

describe("ChatPanel", () => {
  test("refine 內部提示詞不會出現在聊天室，並提供清除內容按鈕", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[
          { role: "user", content: RUBRIC_POLISH_PROMPT },
          { role: "assistant", content: "已完成潤飾，請確認提案。" },
        ]}
        onSendMessage={() => {}}
        onClearMessages={() => {}}
        isLoading={false}
        hasRubric
      />,
    );

    expect(html).not.toContain(RUBRIC_POLISH_PROMPT);
    expect(html).toContain("已完成潤飾，請確認提案。");
    expect(html).toContain("清除內容");
  });

  test("在聊天室提供 AI 一鍵整理與資料來源入口，並在停留時說明用途", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        onToggleSources={() => {}}
        isLoading={false}
        hasRubric
      />,
    );

    expect(html).toContain(">AI一鍵整理</button>");
    expect(html).toContain('title="(好用) AI幫助你把評分表規則化，後續方便腳本生成"');
    expect(html).toContain("資料來源");
    expect(html).toContain('aria-controls="ai-chat-data-sources"');
    expect(html).not.toContain("評分表來源");
    expect(html).not.toContain("自動檢測支援");
  });

  test("資料來源在聊天室內展開，不建立額外 dialog", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        onToggleSources={() => {}}
        sourcesOpen
        sourcesContent={<div>目前資料來源內容</div>}
        isLoading={false}
        hasRubric
      />,
    );

    expect(html).toContain('id="ai-chat-data-sources"');
    expect(html).toContain("目前資料來源內容");
    expect(html).toContain('aria-expanded="true"');
    expect(html).not.toContain('role="dialog"');
  });

  test("以加號提供聊天室附件入口並顯示待送出附件橫欄", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        onUploadFile={() => {}}
        pendingAttachments={[{
          id: "attachment-1",
          original_filename: "requirements.md",
          status: "ready",
        }]}
        isLoading={false}
      />,
    );

    expect(html).toContain('aria-label="新增附件"');
    expect(html).toContain("requirements.md");
    expect(html).toContain("已讀取");
  });

  test("聊天室整合製作檢查腳本按鈕，有評分表時才可點擊", () => {
    const withScript = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        isLoading={false}
        hasRubric
        onCreateScript={() => {}}
        canCreateScript
      />,
    );

    expect(withScript).toContain("製作檢查腳本");
    expect(withScript).not.toContain("匯出 Excel");
    expect(withScript).not.toContain("匯出中");

    const withoutItems = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        isLoading={false}
        hasRubric
        onCreateScript={() => {}}
        canCreateScript={false}
        createScriptHint="請先新增至少一個檢查項目"
      />,
    );

    expect(withoutItems).toContain("製作檢查腳本");
    expect(withoutItems).toContain("disabled");
    expect(withoutItems).toContain('title="請先新增至少一個檢查項目"');
  });

  test("沒有評分表時不提供製作檢查腳本入口", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        isLoading={false}
      />,
    );

    expect(html).not.toContain("製作檢查腳本");
    expect(html).not.toContain("匯出 Excel");
  });

  test("製作中時顯示製作中狀態", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        isLoading={false}
        hasRubric
        onCreateScript={() => {}}
        isCreatingScript
        canCreateScript
      />,
    );

    expect(html).toContain("製作中...");
  });

  test("腳本製作中顯示可辨識的 workflow 狀態與進度動畫標記", () => {
    const html = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        onSendMessage={() => {}}
        isLoading={false}
        hasRubric
        onCreateScript={() => {}}
        isCreatingScript
        scriptGenerationStatus="policy_review"
        canCreateScript
      />,
    );

    expect(html).toContain("安全檢查中…");
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('data-generation-status="policy_review"');
  });

  test("腳本製作失敗會留下可辨識的頁面狀態，不只依賴 toast", () => {
    const html = renderToStaticMarkup(
      <ScriptGenerationNotice
        notice={{
          status: "error",
          message: "上游服務逾時。可再次按「製作檢查腳本」重試。",
        }}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain('data-workflow-status="error"');
    expect(html).toContain("上游服務逾時");
    expect(html).toContain("再次按");
  });

  test("腳本製作中的橙色橫幅沿用旋轉圖示與忙碌狀態", () => {
    const html = renderToStaticMarkup(
      <ScriptGenerationNotice isCreatingScript status="generating" />,
    );

    expect(html).toContain("正在製作檢查腳本");
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('data-workflow-status="generating"');
    expect(html).toContain("spinning");
  });
});

describe("CreateCheckChooser", () => {
  test("新增檢查提供從零建立與已有文件兩條入口", () => {
    const html = renderToStaticMarkup(
      <CreateCheckChooser onChoose={() => {}} onCancel={() => {}} />,
    );

    expect(html).toContain("從零開始建立");
    expect(html).toContain("使用已有評分文件");
    expect(html).toContain("選擇文件");
  });
});

describe("RubricTable", () => {
  const items = [
    {
      id: "python-version",
      title: "Python 版本檢查",
      description: "Python 需要至少 3.11",
      detectable: "auto",
      detection_method: "執行 python --version",
      fallback: "無法執行時由老師確認",
      check_steps: [{ template_key: "python", command_key: "python_version", command_label: "Python 版本" }],
    },
    {
      id: "response-quality",
      title: "回傳內容品質",
      description: "回傳內容符合規格",
      detectable: "partial",
      detection_method: null,
      fallback: "請補充實際輸出格式",
      missing_information: ["預期輸出格式"],
      check_steps: [],
    },
    {
      id: "manual-review",
      title: "主觀設計品質",
      description: "需要老師依作品判斷",
      detectable: "manual",
      detection_method: null,
      fallback: null,
      check_steps: [],
    },
  ];

  test("以最左側圖示提供檢查設定入口", () => {
    const html = renderToStaticMarkup(
      <RubricTable items={items} onChange={() => {}} onDelete={() => {}} />,
    );

    expect(html).toContain("檢查點");
    expect(html).toContain("評分標準");
    expect(html).toContain("自動檢測支援");
    expect(html).toContain('value="Python 版本檢查"');
    expect(html).toContain("能自動檢測");
    expect(html).toContain("缺少資訊");
    expect(html).toContain("不支援");
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-label="展開第 1 項檢查設定"');
    expect(html.indexOf('aria-label="展開第 1 項檢查設定"')).toBeLessThan(html.indexOf('value="Python 版本檢查"'));
    expect(html).not.toContain(">詳細</button>");
    expect(html).not.toContain("執行 python --version");
    expect(html).not.toContain("AI 偵測判斷（僅由 AI 更新）");
  });

  test("只在異動的檢查項目列標示待更新", () => {
    const html = renderToStaticMarkup(
      <RubricTable
        items={items}
        needsReviewIds={new Set(["python-version"])}
        onChange={() => {}}
        onDelete={() => {}}
      />,
    );

    expect(html).toContain("待更新");
    expect(html).toContain('title="缺少資訊（自動檢測支援待更新）"');
    expect(html).toContain("warning_amber");
  });
});

describe("getScriptCreationBlocker", () => {
  const completeItem = {
    id: "python-run",
    title: "執行 main.py",
    detectable: "auto",
    detection_method: "依 exit code 與 stdout 判定",
    check_steps: [{
      template_key: "python",
      command_key: "python.run_entrypoint",
      parameters: {
        cwd: "/home/student/project",
        argv: ["python3", "main.py"],
        timeout_seconds: 30,
        success_criteria: "exit code 為 0 且 stdout 等於 20",
      },
    }],
  };

  test("所有項目都能自動檢測時允許製作腳本", () => {
    expect(getScriptCreationBlocker({ analysis: { items: [completeItem] } })).toBeNull();
  });

  test("缺少資訊或不支援自動檢測時阻擋整份腳本", () => {
    const blocker = getScriptCreationBlocker({
      analysis: {
        items: [
          { ...completeItem, id: "missing", detectable: "partial" },
          { ...completeItem, id: "manual", detectable: "manual" },
        ],
      },
    });

    expect(blocker).toContain("1 項缺少資訊");
    expect(blocker).toContain("1 項不支援自動檢測");
  });

  test("異動後尚未重新確認時阻擋腳本", () => {
    expect(getScriptCreationBlocker({
      analysis: { items: [completeItem], detectability_needs_review: true },
    })).toContain("待更新");
  });

  test("待重新確認項目會從評分表狀態還原，讓提示與列標籤一致", () => {
    const analysis = {
      items: [completeItem],
      detectability_needs_review: true,
    };
    expect([...getRubricReviewItemIds(analysis)]).toEqual(["python-run"]);

    const html = renderToStaticMarkup(
      <RubricTable
        items={analysis.items}
        needsReviewIds={getRubricReviewItemIds(analysis)}
        onChange={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(html).toContain("待更新");
    expect(html).toContain('title="缺少資訊（自動檢測支援待更新）"');
  });

  test("保存的待更新項目只標示對應列，不讓整張表變成待確認", () => {
    const secondItem = { ...completeItem, id: "second-item", title: "第二項" };
    const analysis = {
      items: [completeItem, secondItem],
      detectability_needs_review: true,
      pending_review_item_ids: ["python-run"],
    };

    const html = renderToStaticMarkup(
      <RubricTable
        items={analysis.items}
        needsReviewIds={getRubricReviewItemIds(analysis)}
        onChange={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(html.match(/自動檢測支援待更新/g)).toHaveLength(1);
  });
});

describe("rubric item change detection", () => {
  test("相同項目內容不視為異動，實際欄位變更才產生不同快照", () => {
    const saved = {
      items: [{ id: "item-1", title: "檢查版本", description: "至少 3.11", detectable: "auto" }],
      detectability_needs_review: false,
    };
    const same = { ...saved, detectability_needs_review: true };
    const changed = {
      ...saved,
      items: [{ ...saved.items[0], title: "檢查 Python 版本" }],
    };

    expect(getRubricItemsValue(same)).toBe(getRubricItemsValue(saved));
    expect(getRubricItemsValue(changed)).not.toBe(getRubricItemsValue(saved));
  });

  test("只回傳實際變動的項目 ID，不把整張表標成待更新", () => {
    const savedItems = [
      { id: "item-1", title: "檢查版本", description: "至少 3.11", detectable: "auto" },
      { id: "item-2", title: "檢查輸出", description: "符合格式", detectable: "partial" },
    ];
    const currentItems = [
      { ...savedItems[0], title: "檢查 Python 版本" },
      savedItems[1],
    ];

    expect([...getPendingRubricItemIds(currentItems, savedItems)]).toEqual(["item-1"]);
    expect([...getPendingRubricItemIds([savedItems[1]], savedItems)]).toEqual([]);
  });
});

describe("buildProposalDiff", () => {
  test("將 AI 修改轉成可確認差異，且未回傳項目不會被默認刪除", () => {
    const current = [
      { id: "keep", title: "保留", description: "原內容", detectable: "manual" },
      { id: "remove", title: "移除", description: "舊項目", detectable: "manual" },
    ];
    const diff = buildProposalDiff(current, [
      { id: "keep", title: "保留", description: "新內容", detectable: "manual" },
      { id: "new", title: "新增", description: "新項目", detectable: "auto" },
      { id: "remove", operation: "delete", title: "移除" },
    ]);

    expect(diff.map((item) => [item.id, item.operation])).toEqual([
      ["keep", "update"],
      ["new", "add"],
      ["remove", "delete"],
    ]);
  });
});

describe("uploaded rubric naming", () => {
  test("匯入檔名移除副檔名，且檢查名稱保留檔名主體並限制長度", () => {
    expect(getRubricDisplayName({ name: "AI評分表審核系統_Python服務Running狀態檢測_簡短版.docx" }))
      .toBe("AI評分表審核系統_Python服務Running狀態檢測_簡短版");
    expect(getRubricCheckTitle({ original_filename: "保存的評分表.docx" })).toBe("保存的評分表");
    expect(getRubricCheckTitle({ display_name: "自訂評分表", original_filename: "保存的評分表.docx" })).toBe("自訂評分表");
    expect(getRubricCheckTitle({ name: "  " })).toBe("未命名檢查");
    expect(getRubricCheckTitle({ name: "a".repeat(300) })).toHaveLength(255);
  });
});

describe("session menu positioning", () => {
  test("浮動選單會貼近觸發按鈕並限制在視窗內", () => {
    expect(getSessionMenuPosition(
      { top: 160, right: 780, bottom: 196 },
      { width: 800, height: 600, menuWidth: 220, menuHeight: 280, margin: 12 },
    )).toEqual({ top: 208, left: 560 });

    expect(getSessionMenuPosition(
      { top: 520, right: 790, bottom: 556 },
      { width: 800, height: 600, menuWidth: 220, menuHeight: 280, margin: 12 },
    )).toEqual({ top: 228, left: 568 });
  });
});

describe("SessionTitle", () => {
  test("保留完整名稱作為 tooltip，並將可視區與文字分開以支援截斷動畫", () => {
    const title = "這是一個很長的 AI 檢查 session 名稱";
    const html = renderToStaticMarkup(<SessionTitle title={title}>{title}</SessionTitle>);

    expect(html).toContain('title="這是一個很長的 AI 檢查 session 名稱"');
    expect(html).toContain(title);
  });
});

describe("getSelectedRubricSource", () => {
  const files = [
    { id: "file-other", status: "active", display_name: "其他檢查" },
    { id: "file-selected", status: "active", display_name: "目前檢查" },
    { id: "file-replaced", status: "replaced", display_name: "已取代來源" },
  ];

  test("只回傳目前檢查選用的 active 來源", () => {
    expect(getSelectedRubricSource(files, "file-selected")).toEqual(files[1]);
    expect(getSelectedRubricSource(files, "file-other")).toEqual(files[0]);
  });

  test("沒有選用來源或來源已失效時不回傳其他班級來源", () => {
    expect(getSelectedRubricSource(files, null)).toBeNull();
    expect(getSelectedRubricSource(files, "file-replaced")).toBeNull();
  });
});

describe("resolveActiveSessionId", () => {
  const sessions = [{ id: "session-1" }, { id: "session-2" }];

  test("沒有目前選擇時保持未選取，不自動帶入第一筆檢查", () => {
    expect(resolveActiveSessionId(null, sessions)).toBeNull();
  });

  test("保留仍存在的選擇，清除已不存在的選擇", () => {
    expect(resolveActiveSessionId("session-2", sessions)).toBe("session-2");
    expect(resolveActiveSessionId("session-missing", sessions)).toBeNull();
  });
});

describe("script creation workflow", () => {
  test("通過自動檢查後進入執行結果，失敗時進入腳本總覽", () => {
    expect(getScriptCreationDestination({ status: "approved" })).toBe("execution");
    expect(getScriptCreationDestination({ status: "review_failed", id: "script-1" })).toBe("scripts");
  });
});
