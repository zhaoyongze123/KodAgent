"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Cloud,
  FileUp,
  Folder,
  FolderPlus,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  UsersRound,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  accessLabel,
  libraryStatus,
  normalizeAclSelection,
} from "@/lib/knowledge-source";

type Library = {
  libraryId: number;
  name: string;
  sourceKind: "KOD_FOLDER" | "LOCAL_UPLOAD";
  folderId?: number | null;
  accessMode: string;
  status: "ACTIVE" | "DISABLED";
  lastSyncAt?: string | null;
  lastSyncStatus?: string | null;
  lastErrorCode?: string | null;
  documentCount?: number;
  readyCount?: number;
};

type FolderItem = { folderID?: number; folderId?: number; name: string };
type FolderBrowser = {
  folder?: FolderItem;
  folders?: FolderItem[];
};
type Subject = { id: number; name: string; departmentId?: number | null };

function asErrorMessage(body: unknown, fallback: string) {
  if (body && typeof body === "object") {
    const value = body as Record<string, unknown>;
    for (const key of ["message", "msg", "error", "detail"]) {
      if (typeof value[key] === "string" && value[key]) return value[key];
    }
  }
  return fallback;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (typeof body?.code === "number" && body.code !== 0)) {
    throw new Error(asErrorMessage(body, `请求失败（${response.status}）`));
  }
  if (body && typeof body === "object" && "data" in body) {
    return (body as { data: T }).data;
  }
  return body as T;
}

function folderId(item?: FolderItem | null) {
  const value = item?.folderID ?? item?.folderId;
  return typeof value === "number" && value > 0 ? value : null;
}

function formatDate(value?: string | null) {
  if (!value) return "未同步";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

function sourceKindLabel(kind: Library["sourceKind"]) {
  return kind === "KOD_FOLDER" ? "KodCloud 目录" : "本地上传";
}

function SourceState({ library }: { library: Library }) {
  const label = libraryStatus(library.status, library.lastSyncStatus);
  const failed = label === "同步失败";
  const disabled = label === "已停用";
  const color = failed
    ? "border-rose-200 bg-rose-50 text-rose-700"
    : disabled
      ? "border-slate-200 bg-slate-50 text-slate-500"
      : label === "可检索"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  return <span className={`inline-flex rounded border px-1.5 py-0.5 text-xs ${color}`}>{label}</span>;
}

export default function KnowledgePage() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [disablingId, setDisablingId] = useState<number | null>(null);
  const [folderSheetOpen, setFolderSheetOpen] = useState(false);
  const [uploadSheetOpen, setUploadSheetOpen] = useState(false);
  const [folderTree, setFolderTree] = useState<FolderBrowser | null>(null);
  const [folderLoading, setFolderLoading] = useState(false);
  const [folderSubmitLoading, setFolderSubmitLoading] = useState(false);
  const [folderLookup, setFolderLookup] = useState("");
  const [selectedFolder, setSelectedFolder] = useState<FolderItem | null>(null);
  const [folderName, setFolderName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [accessMode, setAccessMode] = useState<"ALL" | "CUSTOM">("ALL");
  const [userQuery, setUserQuery] = useState("");
  const [departmentQuery, setDepartmentQuery] = useState("");
  const [users, setUsers] = useState<Subject[]>([]);
  const [departments, setDepartments] = useState<Subject[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const initialLoadStarted = useRef(false);

  const ensureSession = useCallback(async () => {
    const response = await fetch("/api/auth/kod-sso/session", { cache: "no-store" });
    if (response.status === 401) {
      const currentPath = `${window.location.pathname}${window.location.search}`;
      window.location.replace(`/auth/kod-sso?tenantId=1&redirectPath=${encodeURIComponent(currentPath)}`);
      return false;
    }
    if (!response.ok) throw new Error("登录状态暂时无法确认");
    const body = await response.json().catch(() => ({}));
    if (body?.authenticated !== true) throw new Error("登录状态无效，请重新登录");
    return true;
  }, []);

  const loadLibraries = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (!(await ensureSession())) return;
      const data = await requestJson<Library[]>("/api/agent-knowledge/libraries");
      setLibraries(Array.isArray(data) ? data : []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "知识源暂时无法加载";
      setLoadError(message);
    } finally {
      setLoading(false);
    }
  }, [ensureSession]);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void loadLibraries();
  }, [loadLibraries]);

  const loadFolder = useCallback(async (id?: number | null) => {
    setFolderLoading(true);
    try {
      const query = id ? `?folderId=${encodeURIComponent(String(id))}` : "";
      const result = await requestJson<FolderBrowser>(`/api/agent-knowledge/libraries/browse${query}`);
      setFolderTree(result);
      if (id && folderId(result.folder) === id) {
        setSelectedFolder(result.folder ?? null);
        setFolderName((name) => name || result.folder?.name || "");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "目录暂时无法读取");
    } finally {
      setFolderLoading(false);
    }
  }, []);

  const openFolderSheet = () => {
    setSelectedFolder(null);
    setFolderName("");
    setFolderLookup("");
    setFolderTree(null);
    setFolderSheetOpen(true);
    void loadFolder();
  };

  const selectFolder = (item: FolderItem) => {
    setSelectedFolder(item);
    setFolderName(item.name);
    const id = folderId(item);
    if (id) setFolderLookup(String(id));
  };

  const createFolderSource = async (event: FormEvent) => {
    event.preventDefault();
    const id = folderId(selectedFolder) ?? Number(folderLookup);
    if (!Number.isInteger(id) || id <= 0) {
      toast.error("请先选择一个可访问目录，或输入有效目录编号后定位");
      return;
    }
    setFolderSubmitLoading(true);
    try {
      await requestJson("/api/agent-knowledge/libraries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folderId: id, name: folderName.trim() }),
      });
      toast.success("目录已加入知识源并完成首次同步");
      setFolderSheetOpen(false);
      await loadLibraries();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "添加目录失败");
    } finally {
      setFolderSubmitLoading(false);
    }
  };

  const loadSubjects = useCallback(async (kind: "users" | "departments", keyword = "") => {
    try {
      const result = await requestJson<Subject[]>(
        `/api/agent-knowledge/libraries/subjects?kind=${kind}&keyword=${encodeURIComponent(keyword)}`,
      );
      if (kind === "users") setUsers(Array.isArray(result) ? result : []);
      else setDepartments(Array.isArray(result) ? result : []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "候选范围无法加载");
    }
  }, []);

  const openUploadSheet = () => {
    setFile(null);
    setUploadName("");
    setAccessMode("ALL");
    setUserQuery("");
    setDepartmentQuery("");
    setSelectedUserIds([]);
    setSelectedDepartmentIds([]);
    setUploadSheetOpen(true);
    void Promise.all([loadSubjects("users"), loadSubjects("departments")]);
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] ?? null;
    setFile(next);
    if (next && !uploadName.trim()) setUploadName(next.name.replace(/\.[^.]+$/, ""));
  };

  const toggleSelection = (id: number, selected: string[], update: (values: string[]) => void) => {
    const value = String(id);
    update(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  };

  const uploadSource = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      toast.error("请选择要导入的资料文件");
      return;
    }
    const acl = normalizeAclSelection(selectedUserIds, selectedDepartmentIds);
    if (accessMode === "CUSTOM" && acl.userIds.length + acl.departmentIds.length === 0) {
      toast.error("指定范围至少需要选择一个部门或人员");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", uploadName.trim());
      form.append("accessMode", accessMode);
      for (const id of acl.userIds) form.append("userIds", String(id));
      for (const id of acl.departmentIds) form.append("departmentIds", String(id));
      await requestJson("/api/agent-knowledge/libraries/uploads", { method: "POST", body: form });
      toast.success("资料已受控导入并完成首次同步");
      setUploadSheetOpen(false);
      await loadLibraries();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "资料导入失败");
    } finally {
      setUploading(false);
    }
  };

  const syncLibrary = async (library: Library) => {
    setSyncingId(library.libraryId);
    try {
      const result = await requestJson<{ status?: string; indexed?: number }>(
        `/api/agent-knowledge/libraries/${library.libraryId}/sync`,
        { method: "POST" },
      );
      if (result.status === "FAILED") throw new Error("同步失败，请检查目录权限或文件格式");
      toast.success(`同步完成${typeof result.indexed === "number" ? `，已索引 ${result.indexed} 份资料` : ""}`);
      await loadLibraries();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "同步失败");
    } finally {
      setSyncingId(null);
    }
  };

  const disableLibrary = async (library: Library) => {
    if (!window.confirm(`停用“${library.name}”？它的派生全文和向量索引会立即失效。`)) return;
    setDisablingId(library.libraryId);
    try {
      await requestJson(`/api/agent-knowledge/libraries/${library.libraryId}`, { method: "DELETE" });
      toast.success("知识源已停用，派生索引已失效");
      await loadLibraries();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "停用失败");
    } finally {
      setDisablingId(null);
    }
  };

  const activeCount = useMemo(
    () => libraries.filter((library) => library.status === "ACTIVE").length,
    [libraries],
  );

  return (
    <main className="min-h-dvh bg-white px-4 py-5 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-5 flex flex-col gap-3 border-b border-slate-200 pb-4 md:flex-row md:items-end md:justify-between">
          <div>
            <Button asChild variant="ghost" size="sm" className="-ml-2 mb-2 text-slate-500">
              <Link href="/"><ArrowLeft className="size-4" aria-hidden="true" />返回对话</Link>
            </Button>
            <div className="flex items-center gap-2.5">
              <div className="flex size-9 items-center justify-center border border-sky-200 bg-sky-50 text-sky-700">
                <ShieldCheck className="size-4" aria-hidden="true" />
              </div>
              <div>
                <h1 className="text-lg font-semibold">知识源管理</h1>
                <p className="mt-0.5 text-sm text-slate-500">集中维护 Agent 可检索的目录和资料，检索时仍按当前用户权限复核。</p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => void loadLibraries()} disabled={loading}>
              <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />刷新
            </Button>
            <Button variant="outline" size="sm" onClick={openFolderSheet}>
              <FolderPlus className="size-4" aria-hidden="true" />添加 KodCloud 目录
            </Button>
            <Button size="sm" onClick={openUploadSheet}>
              <FileUp className="size-4" aria-hidden="true" />上传资料
            </Button>
          </div>
        </header>

        <div className="mb-4 grid grid-cols-2 border border-slate-200 md:grid-cols-4">
          <div className="border-r border-slate-200 px-3 py-2.5"><p className="text-xs text-slate-500">知识源</p><p className="mt-1 text-lg font-semibold tabular-nums">{libraries.length}</p></div>
          <div className="border-r border-slate-200 px-3 py-2.5"><p className="text-xs text-slate-500">运行中</p><p className="mt-1 text-lg font-semibold tabular-nums">{activeCount}</p></div>
          <div className="border-r border-t border-slate-200 px-3 py-2.5 md:border-t-0"><p className="text-xs text-slate-500">已索引资料</p><p className="mt-1 text-lg font-semibold tabular-nums">{libraries.reduce((sum, item) => sum + (item.readyCount ?? 0), 0)}</p></div>
          <div className="border-t border-slate-200 px-3 py-2.5 md:border-t-0"><p className="text-xs text-slate-500">待处理</p><p className="mt-1 text-lg font-semibold tabular-nums">{libraries.reduce((sum, item) => sum + Math.max(0, (item.documentCount ?? 0) - (item.readyCount ?? 0)), 0)}</p></div>
        </div>

        {loadError ? (
          <div role="alert" className="mb-4 flex items-start justify-between gap-4 border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800">
            <span>{loadError}</span>
            <Button size="sm" variant="outline" onClick={() => void loadLibraries()}>重试</Button>
          </div>
        ) : null}

        <section aria-label="知识源列表" className="overflow-hidden border border-slate-200">
          <div className="hidden grid-cols-[minmax(220px,2.2fr)_120px_150px_100px_120px_190px] items-center gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500 lg:grid">
            <span>来源</span><span>类型</span><span>访问范围</span><span>资料</span><span>最近同步</span><span className="text-right">操作</span>
          </div>
          {loading ? Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="m-3 h-12" />) : null}
          {!loading && libraries.length === 0 ? (
            <div className="px-4 py-14 text-center text-sm text-slate-500">
              <Folder className="mx-auto mb-3 size-5 text-slate-400" aria-hidden="true" />
              尚未配置知识源。可添加有权限的 KodCloud 目录，或上传受控资料。
            </div>
          ) : null}
          {!loading && libraries.map((library) => (
            <div key={library.libraryId} className="grid grid-cols-2 gap-x-3 gap-y-2 border-b border-slate-100 px-3 py-3 last:border-b-0 hover:bg-slate-50/70 lg:grid-cols-[minmax(220px,2.2fr)_120px_150px_100px_120px_190px] lg:items-center lg:gap-3 lg:py-2.5">
              <div className="col-span-2 min-w-0 lg:col-span-1"><div className="flex items-center gap-2"><span className="truncate text-sm font-medium">{library.name}</span><SourceState library={library} /></div>{library.lastErrorCode ? <p className="mt-1 truncate text-xs text-rose-600">{library.lastErrorCode}</p> : null}</div>
              <div className="text-xs text-slate-600"><span className="mr-1 text-slate-400 lg:hidden">类型</span>{sourceKindLabel(library.sourceKind)}</div>
              <div className="text-xs text-slate-600"><span className="mr-1 text-slate-400 lg:hidden">范围</span>{accessLabel(library.sourceKind, library.accessMode)}</div>
              <div className="text-sm tabular-nums text-slate-700"><span className="mr-1 text-xs text-slate-400 lg:hidden">资料</span>{library.readyCount ?? 0}/{library.documentCount ?? 0}</div>
              <div className="text-xs text-slate-500"><span className="mr-1 text-slate-400 lg:hidden">同步</span>{formatDate(library.lastSyncAt)}</div>
              <div className="col-span-2 flex justify-end gap-1.5 lg:col-span-1">
                {library.status === "ACTIVE" ? <Button size="sm" variant="outline" onClick={() => void syncLibrary(library)} disabled={syncingId === library.libraryId}>{syncingId === library.libraryId ? <LoaderCircle className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}同步</Button> : null}
                {library.status === "ACTIVE" ? <Button size="sm" variant="ghost" className="text-rose-700 hover:bg-rose-50 hover:text-rose-800" onClick={() => void disableLibrary(library)} disabled={disablingId === library.libraryId}>{disablingId === library.libraryId ? <LoaderCircle className="size-3.5 animate-spin" /> : <XCircle className="size-3.5" />}停用</Button> : null}
              </div>
            </div>
          ))}
        </section>
      </div>

      <Sheet open={folderSheetOpen} onOpenChange={setFolderSheetOpen}>
        <SheetContent className="w-full border-slate-200 sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>添加 KodCloud 目录</SheetTitle>
            <SheetDescription>系统只保存目录编号；同步和检索均会按当前用户的文件夹权限重新校验。</SheetDescription>
          </SheetHeader>
          <form onSubmit={createFolderSource} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4">
            <div className="space-y-2"><Label htmlFor="folder-name">知识源名称</Label><Input id="folder-name" value={folderName} onChange={(event) => setFolderName(event.target.value)} placeholder="默认使用目录名称" /></div>
            <div className="space-y-2"><Label htmlFor="folder-id">目录编号</Label><div className="flex gap-2"><Input id="folder-id" inputMode="numeric" value={folderLookup} onChange={(event) => setFolderLookup(event.target.value)} placeholder="输入已知目录编号" /><Button type="button" variant="outline" onClick={() => void loadFolder(Number(folderLookup))} disabled={folderLoading || !/^\d+$/.test(folderLookup)}><Search className="size-4" aria-hidden="true" />定位</Button></div></div>
            <div className="min-h-48 border border-slate-200">
              <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500"><span className="truncate">{folderTree?.folder?.name ?? "可访问目录"}</span><div className="flex items-center gap-2">{folderLoading ? <LoaderCircle className="size-3.5 animate-spin" /> : null}{folderTree?.folder && folderId(folderTree.folder) ? <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { const currentFolder = folderTree?.folder; if (currentFolder) selectFolder(currentFolder); }}>选择当前目录</Button> : null}</div></div>
              {selectedFolder ? <button type="button" className="flex w-full items-center gap-2 border-b border-sky-100 bg-sky-50 px-3 py-2 text-left text-sm text-sky-800" onClick={() => selectFolder(selectedFolder)}><CheckCircle2 className="size-4" aria-hidden="true" />已选择：{selectedFolder.name}</button> : null}
              {(folderTree?.folders ?? []).map((item) => { const id = folderId(item); return <div key={id ?? item.name} className="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-sm"><Folder className="size-4 shrink-0 text-sky-700" aria-hidden="true" /><span className="min-w-0 flex-1 truncate">{item.name}</span><span className="text-xs text-slate-400">#{id}</span><Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => selectFolder(item)}>选择</Button><Button type="button" size="icon" variant="ghost" aria-label={`进入 ${item.name}`} title={`进入 ${item.name}`} onClick={() => { if (id) void loadFolder(id); }} disabled={!id}><ChevronRight className="size-4" aria-hidden="true" /></Button></div>; })}
              {!folderLoading && !selectedFolder && (folderTree?.folders ?? []).length === 0 ? <p className="px-3 py-6 text-center text-sm text-slate-500">没有可继续浏览的目录，可输入已知目录编号定位。</p> : null}
            </div>
            <SheetFooter className="px-0"><Button type="submit" disabled={folderSubmitLoading}>{folderSubmitLoading ? <LoaderCircle className="size-4 animate-spin" /> : <Cloud className="size-4" />}添加并同步</Button></SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      <Sheet open={uploadSheetOpen} onOpenChange={setUploadSheetOpen}>
        <SheetContent className="w-full border-slate-200 sm:max-w-xl">
          <SheetHeader><SheetTitle>上传本地资料</SheetTitle><SheetDescription>资料二进制受控保存，不生成公开链接。每份资料可独立授权。</SheetDescription></SheetHeader>
          <form onSubmit={uploadSource} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4">
            <div className="space-y-2"><Label htmlFor="knowledge-file">资料文件</Label><Input id="knowledge-file" type="file" accept=".pdf,.docx,.xlsx,.txt,.md,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={onFileChange} />{file ? <p className="text-xs text-slate-500">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</p> : null}</div>
            <div className="space-y-2"><Label htmlFor="upload-name">资料名称</Label><Input id="upload-name" value={uploadName} onChange={(event) => setUploadName(event.target.value)} placeholder="默认使用文件名" /></div>
            <fieldset className="space-y-2"><legend className="text-sm font-medium">访问范围</legend><label className="flex cursor-pointer items-center gap-2 border border-slate-200 px-3 py-2 text-sm"><input type="radio" name="access" checked={accessMode === "ALL"} onChange={() => setAccessMode("ALL")} />全员可检索</label><label className="flex cursor-pointer items-center gap-2 border border-slate-200 px-3 py-2 text-sm"><input type="radio" name="access" checked={accessMode === "CUSTOM"} onChange={() => setAccessMode("CUSTOM")} />指定部门和人员</label></fieldset>
            {accessMode === "CUSTOM" ? <div className="grid gap-3 md:grid-cols-2"><div className="border border-slate-200"><div className="border-b border-slate-200 p-2"><Label htmlFor="user-search" className="text-xs">人员</Label><Input id="user-search" className="mt-1 h-8" value={userQuery} onChange={(event) => { setUserQuery(event.target.value); void loadSubjects("users", event.target.value); }} placeholder="搜索人员" /></div><div className="max-h-44 overflow-y-auto">{users.map((item) => <label key={item.id} className="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-2 py-1.5 text-sm"><input type="checkbox" checked={selectedUserIds.includes(String(item.id))} onChange={() => toggleSelection(item.id, selectedUserIds, setSelectedUserIds)} />{item.name}</label>)}</div></div><div className="border border-slate-200"><div className="border-b border-slate-200 p-2"><Label htmlFor="dept-search" className="text-xs">部门</Label><Input id="dept-search" className="mt-1 h-8" value={departmentQuery} onChange={(event) => { setDepartmentQuery(event.target.value); void loadSubjects("departments", event.target.value); }} placeholder="搜索部门" /></div><div className="max-h-44 overflow-y-auto">{departments.map((item) => <label key={item.id} className="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-2 py-1.5 text-sm"><input type="checkbox" checked={selectedDepartmentIds.includes(String(item.id))} onChange={() => toggleSelection(item.id, selectedDepartmentIds, setSelectedDepartmentIds)} />{item.name}</label>)}</div></div></div> : null}
            <div className="border border-sky-100 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-900"><UsersRound className="mr-1 inline size-3.5" aria-hidden="true" />上传后会进入同一检索管道；文件删除或知识源停用后，全文和向量派生副本会失效。</div>
            <SheetFooter className="px-0"><Button type="submit" disabled={uploading}>{uploading ? <LoaderCircle className="size-4 animate-spin" /> : <FileUp className="size-4" />}导入并同步</Button></SheetFooter>
          </form>
        </SheetContent>
      </Sheet>
    </main>
  );
}
