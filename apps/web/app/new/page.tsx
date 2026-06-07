"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthRequiredMessage, isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
import { api } from "@/lib/api";
import { hasUsableLlmSettings, loadLlmSettings } from "@/lib/llm-settings";
import { LANGUAGE_OPTIONS, type AdaptationType, type Language } from "@/lib/types";

const SAMPLE_NOVEL = `# 示例小说：雨夜来客

## 第一章 雨夜敲门

林屿关上诊所的灯，刚想熄掉门廊的最后一盏台灯，卷帘门外传来一阵急促的敲击声。

他犹豫了三秒，雨水正顺着门缝渗进来。

"今天已经停诊了。"他隔着门说。

门外的人没有回答，只是又敲了三下。林屿叹了口气，拉起卷帘门。

站在门外的女人浑身湿透，黑色大衣下渗出暗红色的液体。她什么也没说，径直倒进林屿怀里。

## 第二章 失忆的来客

女人醒来时，已经是第二天下午。

"你是谁？"林屿问。

"我不记得。"她盯着天花板，眼神发空。

林屿翻了翻她身上的物件——一张没写姓名的名片、一枚旧式钥匙、还有一张被水泡得模糊的合照。

"你身上有刀伤，但伤口包扎得很专业，"林屿说，"你来自一个有医疗条件的地方。"

女人闭上眼："也许吧。"

## 第三章 旧城诊所的夜晚

那一夜，诊所门外又响起雨声。

女人坐在窗边，第一次开口讲了一段话：

"我来找一个人，他三个月前从这座城市消失。"

林屿抬起头："谁？"

"我自己。"
`;

type CreationMode = "novel" | "script_source";
type ScriptSourceFormat = "yaml" | "json";

export default function NewProjectPage() {
  const router = useRouter();
  const [mode, setMode] = useState<CreationMode>("novel");
  const [title, setTitle] = useState("雨夜来客");
  const [text, setText] = useState("");
  const [scriptSource, setScriptSource] = useState("");
  const [scriptSourceFormat, setScriptSourceFormat] = useState<ScriptSourceFormat>("yaml");
  const [adaptation, setAdaptation] = useState<AdaptationType>("short_drama");
  const [language, setLanguage] = useState<Language>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadedSourceFileName, setUploadedSourceFileName] = useState<string | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const [keyLoading, setKeyLoading] = useState(true);

  useEffect(() => {
    let alive = true;

    async function refreshKeyStatus() {
      const localReady = hasUsableLlmSettings();
      if (localReady) {
        if (alive) {
          setHasKey(true);
          setKeyLoading(false);
        }
        return;
      }

      try {
        const activeKey = await api.getActiveModelKey();
        if (alive) setHasKey(Boolean(activeKey && activeKey.status === "active"));
      } catch {
        if (alive) setHasKey(false);
      } finally {
        if (alive) setKeyLoading(false);
      }
    }

    void refreshKeyStatus();
    return () => {
      alive = false;
    };
  }, []);

  const characterCount = text.trim().length;
  const scriptSourceCharacterCount = scriptSource.trim().length;
  const chapterMarkerCount = (
    text.match(/(^|\n)\s*(#{1,6}\s*)?(第[一二三四五六七八九十百千万0-9]+章|Chapter\s+\d+)/gi) ?? []
  ).length;

  function loadSample() {
    setTitle("雨夜来客");
    setText(SAMPLE_NOVEL);
    setUploadedFileName(null);
    setError(null);
  }

  async function uploadNovelFile(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    if (!file) return;

    const fileName = file.name;
    if (!/\.(txt|md)$/i.test(fileName)) {
      setError("请上传 .txt 或 .md 文件。");
      input.value = "";
      return;
    }

    try {
      const fileText = await file.text();
      if (!fileText.trim()) {
        throw new Error("文件内容为空，请换一个包含小说正文的文件。");
      }

      setText(fileText);
      setUploadedFileName(fileName);
      if (!title.trim() || title === "雨夜来客") {
        setTitle(fileName.replace(/\.(txt|md)$/i, ""));
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      input.value = "";
    }
  }

  async function uploadScriptSourceFile(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    if (!file) return;

    const fileName = file.name;
    if (!/\.(ya?ml|json)$/i.test(fileName)) {
      setError("请上传 .yaml、.yml 或 .json 剧本源码文件。");
      input.value = "";
      return;
    }

    try {
      const fileText = await file.text();
      if (!fileText.trim()) {
        throw new Error("文件内容为空，请换一个包含剧本源码的文件。");
      }

      setScriptSource(fileText);
      setScriptSourceFormat(/\.json$/i.test(fileName) ? "json" : "yaml");
      setUploadedSourceFileName(fileName);
      if (!title.trim() || title === "雨夜来客") {
        setTitle(fileName.replace(/\.(ya?ml|json)$/i, ""));
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      input.value = "";
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (mode === "script_source") {
      if (!scriptSource.trim()) {
        setError("请先粘贴或上传剧本源码。");
        return;
      }
      setBusy(true);
      try {
        const res = await api.importScriptProject({
          title: title.trim() || undefined,
          content: scriptSource,
          format: scriptSourceFormat,
        });
        router.push(`/projects/${res.project_id}/edit`);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
      return;
    }

    const llm = loadLlmSettings();
    if (!hasUsableLlmSettings(llm) && !hasKey) {
      setError("请先在“模型设置”保存云端或本地 API key。");
      return;
    }
    setBusy(true);
    try {
      const res = await api.createProject({
        title,
        raw_text: text,
        adaptation_type: adaptation,
        language: language === "auto" ? undefined : language,
      });
      const run = await api.generate(res.project_id, llm);
      router.push(`/runs/${run.run_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">创建项目</h1>
        <p className="mt-1 text-sm text-ink-400">
          从小说原文启动 AI 改编，或直接导入已经导出的剧本源码。
        </p>
      </div>

      <div className="card space-y-4">
        <div className="grid grid-cols-2 gap-2 rounded-md border border-ink-600/40 bg-ink-900 p-1">
          <button
            type="button"
            className={mode === "novel" ? "btn-primary px-3 py-2 text-sm" : "btn-ghost px-3 py-2 text-sm"}
            onClick={() => {
              setMode("novel");
              setError(null);
            }}
          >
            小说转剧本
          </button>
          <button
            type="button"
            className={mode === "script_source" ? "btn-primary px-3 py-2 text-sm" : "btn-ghost px-3 py-2 text-sm"}
            onClick={() => {
              setMode("script_source");
              setError(null);
            }}
          >
            导入剧本源码
          </button>
        </div>

        <div>
          <label className="label" htmlFor="title">项目名</label>
          <input
            id="title"
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={mode === "script_source" ? "可留空，默认使用源码中的剧名" : "例如：雨夜来客"}
            required={mode === "novel"}
          />
        </div>

        {mode === "novel" && (
          <>
            <div>
              <label className="label" htmlFor="adaptation">改编类型</label>
              <select
                id="adaptation"
                className="input"
                value={adaptation}
                onChange={(e) => setAdaptation(e.target.value as AdaptationType)}
              >
                <option value="short_drama">短剧</option>
                <option value="series">连续剧</option>
                <option value="film">电影</option>
                <option value="stage">舞台剧</option>
                <option value="other">其他</option>
              </select>
            </div>

            <div>
              <label className="label" htmlFor="language">输出语言</label>
              <select
                id="language"
                className="input"
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-ink-400">
                “自动检测”会按小说文本的字符分布判断。手动选择可覆盖检测结果。
              </p>
            </div>
          </>
        )}

        {mode === "novel" && <div>
          <div className="flex items-center justify-between">
            <label className="label" htmlFor="text">小说文本</label>
            <div className="flex items-center gap-2">
              <label className="btn-ghost cursor-pointer px-3 py-1.5 text-xs" htmlFor="novel-file">
                上传 .md / .txt
              </label>
              <input
                id="novel-file"
                className="sr-only"
                type="file"
                accept=".md,.txt,text/markdown,text/plain"
                onChange={uploadNovelFile}
              />
              <button
                type="button"
                className="btn-ghost px-3 py-1.5 text-xs"
                onClick={loadSample}
              >
                载入示例
              </button>
            </div>
          </div>
          <textarea
            id="text"
            className="input min-h-[320px] font-mono text-xs leading-relaxed"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="粘贴小说正文，或上传 .md / .txt 文件。"
            required
          />
          <div className="mt-2 flex flex-col gap-1 text-xs text-ink-400 sm:flex-row sm:items-center sm:justify-between">
            <p>提示：使用 “第一章 标题” 或 “## 标题” 标记章节边界。</p>
            <p>
              {uploadedFileName ? `已载入：${uploadedFileName} · ` : ""}
              {characterCount > 0
                ? `${characterCount} 字 · 约 ${chapterMarkerCount} 处章节标记`
                : "等待输入小说正文"}
            </p>
          </div>
        </div>}

        {mode === "script_source" && (
          <div>
            <div className="flex items-center justify-between">
              <label className="label" htmlFor="script-source">剧本源码</label>
              <div className="flex items-center gap-2">
                <select
                  className="input h-8 w-24 py-1 text-xs"
                  value={scriptSourceFormat}
                  onChange={(e) => setScriptSourceFormat(e.target.value as ScriptSourceFormat)}
                >
                  <option value="yaml">YAML</option>
                  <option value="json">JSON</option>
                </select>
                <label className="btn-ghost cursor-pointer px-3 py-1.5 text-xs" htmlFor="script-source-file">
                  上传源码
                </label>
                <input
                  id="script-source-file"
                  className="sr-only"
                  type="file"
                  accept=".yaml,.yml,.json,application/json,text/yaml,text/plain"
                  onChange={uploadScriptSourceFile}
                />
              </div>
            </div>
            <textarea
              id="script-source"
              className="input min-h-[420px] font-mono text-xs leading-relaxed"
              value={scriptSource}
              onChange={(e) => setScriptSource(e.target.value)}
              placeholder="粘贴从剧本工坊导出的 YAML 或 JSON。导入后会直接生成项目快照，不会启动 AI 转换。"
              required={mode === "script_source"}
              spellCheck={false}
            />
            <div className="mt-2 flex flex-col gap-1 text-xs text-ink-400 sm:flex-row sm:items-center sm:justify-between">
              <p>源码导入适合恢复备份或迁移已有剧本；小说原文请使用“小说转剧本”。</p>
              <p>
                {uploadedSourceFileName ? `已载入：${uploadedSourceFileName} · ` : ""}
                {scriptSourceCharacterCount > 0
                  ? `${scriptSourceCharacterCount} 字符 · ${scriptSourceFormat.toUpperCase()}`
                  : "等待输入剧本源码"}
              </p>
            </div>
          </div>
        )}

      {isAuthRequiredMessage(error) ? (
        <AuthRequiredMessage />
      ) : error ? (
        <div className="notice-danger">
          {error}
        </div>
      ) : null}

        {mode === "novel" && !keyLoading && !hasKey && (
          <div className="notice-warning">
            尚未检测到可用模型 key。请先前往{" "}
            <Link href="/settings" className="underline">模型设置</Link>
            ，保存云端或本地 API key 后再回来生成。
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            className="btn-primary"
            disabled={
              busy ||
              (mode === "novel" && (!text || keyLoading || !hasKey)) ||
              (mode === "script_source" && !scriptSource.trim())
            }
          >
            {busy
              ? "提交中…"
              : mode === "script_source"
                ? "导入并进入编辑器"
                : "创建并启动生成"}
          </button>
        </div>
      </div>
    </form>
  );
}
