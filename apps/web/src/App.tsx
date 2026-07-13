import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cloud,
  Download,
  Edit3,
  File as FileIcon,
  FilePlus2,
  Folder,
  FolderOpen,
  FolderPlus,
  HardDrive,
  Home,
  Info,
  LayoutList,
  Lock,
  LogOut,
  MoreHorizontal,
  PanelRight,
  RefreshCw,
  Search,
  Server,
  Shield,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
  CloudUpload,
  ExternalLink,
  KeyRound,
  UserRound,
  RotateCcw,
} from "lucide-react";
import type { DriveItem } from "@teledrive/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  useRef,
  useEffect,
  useMemo,
  useState,
  type DragEvent,
  type FormEvent,
  type MouseEvent,
} from "react";
import {
  createFile,
  createFolder,
  createRecoveryManifest,
  cleanupStaleManifests,
  purgeChannelStorage,
  createServerFolder,
  copyDriveFileToServer,
  deleteFile,
  deletePermanently,
  deletePermanentlyBulk,
  deleteServerFile,
  downloadFile,
  downloadFilesZip,
  downloadServerFile,
  getMe,
  getRegistrationSettings,
  getServerFilesConfig,
  getServerFilesStatus,
  getStorageStatus,
  getUpdateStatus,
  importServerFileToDrive,
  login,
  logout as endSession,
  listFiles,
  listDeletionJobs,
  retryDeletionJobs,
  listServerFiles,
  listTrash,
  register,
  readDriveTextFile,
  readServerTextFile,
  saveTelegramCredentials,
  saveTelegramSession,
  saveServerFilesConfig,
  saveDriveTextFile,
  saveServerTextFile,
  bootstrapSession,
  setCsrfToken,
  setSessionActive,
  startTelegramLogin,
  syncFileToTelegram,
  testServerFilesConfig,
  updateDriveItem,
  updateAccount,
  updateRegistrationSettings,
  updateServerFile,
  restoreFromTrash,
  restoreRecoveryManifest,
  importTelegramRecovery,
  emptyTrash,
  formatApiError,
  formatAuthError,
  uploadFile,
  uploadServerFile,
  verifyTelegramLogin,
  verifyTelegramPassword,
  type ServerFilesConfigPayload,
  type ServerFileItem,
  type SaveTextFilePayload,
  type TextFileContent,
} from "./api";
import { AuthScreen, type AuthMode } from "./AuthScreen";
import { DeletionJobBanners } from "./DeletionJobBanners";
import { DevHealthBadge } from "./DevHealthBadge";
import { TextEditorDialog } from "./TextEditorDialog";

function formatBytes(size: number) {
  if (size === 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** power).toFixed(power === 0 ? 0 : 1)} ${units[power]}`;
}

function formatFileType(item: DriveItem) {
  if (item.kind === "folder") return "Folder";
  const mimeType = item.mimeType?.toLowerCase() ?? "";
  const extension = item.name.split(".").pop()?.toLowerCase();
  const byExtension: Record<string, string> = {
    csv: "CSV",
    doc: "DOC",
    docx: "DOCX",
    gz: "GZIP",
    jpeg: "JPG",
    jpg: "JPG",
    json: "JSON",
    md: "MD",
    mp3: "MP3",
    mp4: "MP4",
    pdf: "PDF",
    png: "PNG",
    ppt: "PPT",
    pptx: "PPTX",
    rar: "RAR",
    txt: "TXT",
    xls: "XLS",
    xlsx: "XLSX",
    zip: "ZIP",
  };
  if (extension && byExtension[extension]) return byExtension[extension];
  if (mimeType.startsWith("image/")) return "Image";
  if (mimeType.startsWith("video/")) return "Video";
  if (mimeType.startsWith("audio/")) return "Audio";
  if (mimeType.includes("spreadsheet") || mimeType.includes("excel")) return "Sheet";
  if (mimeType.includes("presentation") || mimeType.includes("powerpoint")) return "Slide";
  if (mimeType.includes("wordprocessing") || mimeType.includes("word")) return "Document";
  if (mimeType.includes("pdf")) return "PDF";
  if (mimeType.includes("zip") || mimeType.includes("compressed")) return "Archive";
  if (mimeType.startsWith("text/")) return "Text";
  return "File";
}

function parentServerPath(path: string) {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function serverBreadcrumbs(path: string) {
  const parts = path.split("/").filter(Boolean);
  return [
    { name: "Server Files", path: "" },
    ...parts.map((part, index) => ({
      name: part,
      path: parts.slice(0, index + 1).join("/"),
    })),
  ];
}

function serverFileDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : "-";
}

const columnHelper = createColumnHelper<DriveItem>();

type HistoryEntry = { id: string | null; name: string };
type ContextMenu = { x: number; y: number; item: DriveItem } | null;
type SortMode = "name" | "updated" | "size" | "sync";
type ViewMode = "details" | "compact";
type SidePanel = "files" | "server" | "trash" | "access" | "api" | "setup" | "account";
type EditorTarget = (
  | { source: "drive"; id: string; mimeType?: string | null }
  | { source: "server"; path: string }
) & { name: string; size: number };
type EditorSave = { target: EditorTarget; payload: SaveTextFilePayload; revision?: string };

const editableTextExtensions = new Set([
  "bash", "c", "cc", "cfg", "conf", "cpp", "css", "csv", "env", "go", "h", "html", "ini",
  "java", "js", "json", "jsx", "log", "md", "markdown", "php", "py", "rs", "sh", "sql",
  "svg", "toml", "ts", "tsx", "txt", "xml", "yaml", "yml", "zsh",
]);
const maxEditorBytes = 5 * 1024 * 1024;

function isEditableTextFile(item: { name: string; size: number; mimeType?: string | null }) {
  const extension = item.name.split(".").pop()?.toLowerCase();
  return item.size <= maxEditorBytes && (
    editableTextExtensions.has(extension ?? "") || item.mimeType?.toLowerCase().startsWith("text/") === true
  );
}

function sameEditorTarget(left: EditorTarget | null, right: EditorTarget) {
  if (!left || left.source !== right.source) return false;
  return left.source === "drive" && right.source === "drive"
    ? left.id === right.id
    : left.source === "server" && right.source === "server" && left.path === right.path;
}

const sortLabels: Record<SortMode, string> = {
  name: "Name",
  updated: "Modified",
  size: "Size",
  sync: "Sync",
};

export function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [bootstrapping, setBootstrapping] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authError, setAuthError] = useState("");
  const [telegramApiId, setTelegramApiId] = useState("");
  const [telegramApiHash, setTelegramApiHash] = useState("");
  const [telegramPhone, setTelegramPhone] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [telegramPassword, setTelegramPassword] = useState("");
  const [telegramLoginStep, setTelegramLoginStep] = useState<"phone" | "code" | "password" | "done">("phone");
  const [telegramLoginMessage, setTelegramLoginMessage] = useState("");
  const [telegramSession, setTelegramSession] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [accountMessage, setAccountMessage] = useState("");
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
  const [statusRefreshedAt, setStatusRefreshedAt] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [currentFolder, setCurrentFolder] = useState<HistoryEntry>({
    id: null,
    name: "TeleDrive Storage",
  });
  const [history, setHistory] = useState<HistoryEntry[]>([currentFolder]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [path, setPath] = useState<HistoryEntry[]>([currentFolder]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [contextMenu, setContextMenu] = useState<ContextMenu>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [draggedItemId, setDraggedItemId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [trashSelectedIds, setTrashSelectedIds] = useState<string[]>([]);
  const [isBulkDownloading, setIsBulkDownloading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [deleteFeedback, setDeleteFeedback] = useState<
    | { phase: "running"; current: number; total: number; label: string; indeterminate?: boolean }
    | { phase: "success"; count: number; label: string }
    | { phase: "error"; message: string }
    | null
  >(null);
  const [sortMode, setSortMode] = useState<SortMode>("name");
  const [viewMode, setViewMode] = useState<ViewMode>("details");
  const [showDetails, setShowDetails] = useState(true);
  const [sidePanel, setSidePanel] = useState<SidePanel>("files");
  const [serverPath, setServerPath] = useState("");
  const [serverHistory, setServerHistory] = useState<string[]>([""]);
  const [serverHistoryIndex, setServerHistoryIndex] = useState(0);
  const [serverSelectedPath, setServerSelectedPath] = useState<string | null>(null);
  const [serverSelectedPaths, setServerSelectedPaths] = useState<string[]>([]);
  const [serverRenamingPath, setServerRenamingPath] = useState<string | null>(null);
  const [serverRenameValue, setServerRenameValue] = useState("");
  const [serverDraggedPath, setServerDraggedPath] = useState<string | null>(null);
  const [serverDropTargetPath, setServerDropTargetPath] = useState<string | null>(null);
  const [showServerSetup, setShowServerSetup] = useState(false);
  const [serverSetupMessage, setServerSetupMessage] = useState("");
  const [editorTarget, setEditorTarget] = useState<EditorTarget | null>(null);
  const [editorDocument, setEditorDocument] = useState<TextFileContent | null>(null);
  const [editorError, setEditorError] = useState("");
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorConflict, setEditorConflict] = useState(false);
  const [serverConfigForm, setServerConfigForm] = useState<ServerFilesConfigPayload>({
    mode: "sftp",
    localRoot: "./server-files",
    sftpHost: "",
    sftpPort: 22,
    sftpUser: "",
    sftpPassword: "",
    sftpKeyPath: "",
    sftpRoot: "/home/deploy",
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const serverFileInputRef = useRef<HTMLInputElement | null>(null);
  const navigationTargetRef = useRef<string | null>(null);
  const editorRequestRef = useRef(0);
  const lastDriveSelectionIndexRef = useRef<number | null>(null);
  const lastTrashSelectionIndexRef = useRef<number | null>(null);
  const lastServerSelectionIndexRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bootstrapSession().then((authenticated) => {
      if (cancelled) return;
      setToken(authenticated ? "session" : "");
      setBootstrapping(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => {
      setSessionActive(false);
      setToken("");
      setSelectedId(null);
      setSelectedIds([]);
      void queryClient.clear();
    };
    window.addEventListener("teledrive:auth-expired", handleAuthExpired);
    return () => window.removeEventListener("teledrive:auth-expired", handleAuthExpired);
  }, [queryClient]);

  const meQuery = useQuery({
    queryKey: ["me", token],
    queryFn: getMe,
    enabled: Boolean(token),
    retry: false,
  });

  useEffect(() => {
    if (sidePanel === "server" && meQuery.data && !meQuery.data.isOperator) {
      setSidePanel("files");
    }
  }, [meQuery.data, sidePanel]);

  const registrationSettingsQuery = useQuery({
    queryKey: ["registration-settings"],
    queryFn: getRegistrationSettings,
    enabled: Boolean(token) && Boolean(meQuery.data?.isOperator),
    retry: false,
  });
  const deletionJobsQuery = useQuery({
    queryKey: ["deletion-jobs", sidePanel === "trash"],
    queryFn: () => listDeletionJobs(sidePanel === "trash"),
    enabled: Boolean(token) && (sidePanel === "trash" || sidePanel === "account"),
    refetchInterval: sidePanel === "trash" ? 15_000 : false,
    staleTime: 10_000,
  });

  const filesQuery = useQuery({
    queryKey: ["files", currentFolder.id],
    queryFn: () => listFiles(currentFolder.id),
    enabled: Boolean(token),
  });

  const rootFilesQuery = useQuery({
    queryKey: ["files", "root-sidebar"],
    queryFn: () => listFiles(null),
    enabled: Boolean(token),
  });

  const storageQuery = useQuery({
    queryKey: ["storage-status"],
    queryFn: getStorageStatus,
    enabled: Boolean(token),
  });

  const serverStatusQuery = useQuery({
    queryKey: ["server-files-status"],
    queryFn: getServerFilesStatus,
    enabled: Boolean(token),
  });

  const serverConfigQuery = useQuery({
    queryKey: ["server-files-config"],
    queryFn: getServerFilesConfig,
    enabled: Boolean(token),
  });

  const updateStatusQuery = useQuery({
    queryKey: ["update-status"],
    queryFn: getUpdateStatus,
    enabled: Boolean(token),
    refetchInterval: 60 * 60 * 1000,
    staleTime: 15 * 60 * 1000,
    retry: false,
  });

  const serverFilesQuery = useQuery({
    queryKey: ["server-files", serverPath],
    queryFn: () => listServerFiles(serverPath),
    enabled: Boolean(token) && sidePanel === "server",
  });

  const trashQuery = useQuery({
    queryKey: ["trash"],
    queryFn: listTrash,
    enabled: Boolean(token) && sidePanel === "trash",
    refetchOnMount: "always",
  });

  useEffect(() => {
    const config = serverConfigQuery.data;
    if (!config) return;
    setServerConfigForm((current) => ({
      mode: config.mode,
      localRoot: config.localRoot || current.localRoot,
      sftpHost: config.sftpHost || current.sftpHost,
      sftpPort: config.sftpPort || current.sftpPort,
      sftpUser: config.sftpUser || current.sftpUser,
      sftpPassword: "",
      sftpKeyPath: config.sftpKeyPath || current.sftpKeyPath,
      sftpRoot: config.sftpRoot || current.sftpRoot,
    }));
  }, [serverConfigQuery.data]);

  const items = filesQuery.data ?? [];
  const rootItems = rootFilesQuery.data ?? [];
  const status = storageQuery.data;
  const serverStatus = serverStatusQuery.data;
  const updateStatus = updateStatusQuery.data;
  const serverItems = serverFilesQuery.data ?? [];
  const serverSelectedItem = serverSelectedPath
    ? serverItems.find((item) => item.path === serverSelectedPath)
    : undefined;
  const serverSelectedItems = serverItems.filter((item) =>
    serverSelectedPaths.includes(item.path),
  );
  const serverSelectedFiles = serverSelectedItems.filter((item) => item.kind === "file");
  const allServerItemsSelected =
    Boolean(serverItems.length) &&
    serverItems.every((item) => serverSelectedPaths.includes(item.path));
  const serverParentPath = parentServerPath(serverPath);
  const trashItems = trashQuery.data ?? [];
  const pendingDeletionJobs = (deletionJobsQuery.data ?? []).filter(
    (job) => job.status === "pending" || job.status === "processing" || job.status === "failed",
  );
  const failedDeletionJobs = pendingDeletionJobs.filter((job) => job.status === "failed");
  const processingDeletionJobs = pendingDeletionJobs.filter((job) => job.status === "processing");
  const queuedDeletionJobs = pendingDeletionJobs.filter((job) => job.status === "pending");
  const trashSelectedItems = trashItems.filter((item) =>
    trashSelectedIds.includes(item.id),
  );
  const trashSelectedFiles = trashSelectedItems.filter((item) => item.kind === "file");

  const filteredItems = useMemo(() => {
    const visibleItems = items.filter((item) =>
      item.name.toLowerCase().includes(query.toLowerCase()),
    );
    return [...visibleItems].sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "folder" ? -1 : 1;
      if (sortMode === "updated") {
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
      }
      if (sortMode === "size") {
        return b.size - a.size || a.name.localeCompare(b.name);
      }
      if (sortMode === "sync") {
        return a.syncStatus.localeCompare(b.syncStatus) || a.name.localeCompare(b.name);
      }
      return a.name.localeCompare(b.name);
    });
  }, [items, query, sortMode]);

  const selectedItem = selectedId
    ? items.find((item) => item.id === selectedId)
    : undefined;
  const selectedItems = items.filter((item) => selectedIds.includes(item.id));
  const selectedFiles = selectedItems.filter((item) => item.kind === "file");
  const visibleDriveItemIds = filteredItems.map((item) => item.id);
  const allVisibleDriveSelected =
    Boolean(visibleDriveItemIds.length) &&
    visibleDriveItemIds.every((id) => selectedIds.includes(id));
  const totalSize = items.reduce((total, item) => total + item.size, 0);
  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;
  const canGoUp = path.length > 1;
  const canGoServerBack = serverHistoryIndex > 0;
  const canGoServerForward = serverHistoryIndex < serverHistory.length - 1;
  const canGoServerUp = Boolean(serverPath);

  const refreshFiles = async () => {
    await queryClient.invalidateQueries({ queryKey: ["files"] });
    await queryClient.invalidateQueries({ queryKey: ["storage-status"] });
  };

  function navigateTo(entry: HistoryEntry, nextPath: HistoryEntry[]) {
    navigationTargetRef.current = entry.id;
    setCurrentFolder(entry);
    setPath(nextPath);
    setSelectedId(null);
    setSelectedIds([]);
    setQuery("");
    setContextMenu(null);
    setSidePanel("files");
    const trimmedHistory = history.slice(0, historyIndex + 1);
    const lastEntry = trimmedHistory[trimmedHistory.length - 1];
    if (lastEntry?.id !== entry.id) {
      setHistory([...trimmedHistory, entry]);
      setHistoryIndex(trimmedHistory.length);
    }
  }

  async function prepareFolder(entry: HistoryEntry, nextPath: HistoryEntry[]) {
    await queryClient.ensureQueryData({
      queryKey: ["files", entry.id],
      queryFn: () => listFiles(entry.id),
    });
    navigateTo(entry, nextPath);
  }

  function openFolder(folder: DriveItem) {
    if (folder.kind !== "folder") return;
    const entry = { id: folder.id, name: folder.name };
    if (sidePanel === "files" && navigationTargetRef.current === entry.id) return;
    navigationTargetRef.current = entry.id;
    void prepareFolder(entry, [...path, entry]);
  }

  function openRootFolder(folder: DriveItem) {
    if (folder.kind !== "folder") return;
    const entry = { id: folder.id, name: folder.name };
    if (sidePanel === "files" && navigationTargetRef.current === entry.id) return;
    navigationTargetRef.current = entry.id;
    void prepareFolder(entry, [path[0], entry]);
  }

  function goBack() {
    if (!canGoBack) return;
    const nextIndex = historyIndex - 1;
    const entry = history[nextIndex];
    setHistoryIndex(nextIndex);
    setCurrentFolder(entry);
    setSelectedId(null);
    setSelectedIds([]);
    setPath(entry.id ? [path[0], entry] : [path[0]]);
  }

  function goForward() {
    if (!canGoForward) return;
    const nextIndex = historyIndex + 1;
    const entry = history[nextIndex];
    setHistoryIndex(nextIndex);
    setCurrentFolder(entry);
    setSelectedId(null);
    setSelectedIds([]);
    setPath(entry.id ? [path[0], entry] : [path[0]]);
  }

  function goUp() {
    if (!canGoUp) return;
    const nextPath = path.slice(0, -1);
    navigateTo(nextPath[nextPath.length - 1], nextPath);
  }

  const createFolderMutation = useMutation({
    mutationFn: () => createFolder("New folder", currentFolder.id),
    onSuccess: async (folder) => {
      setSelectedId(folder.id);
      setSelectedIds([folder.id]);
      setRenamingId(folder.id);
      setRenameValue(folder.name);
      await refreshFiles();
    },
  });

  const createFileMutation = useMutation({
    mutationFn: (file?: globalThis.File) => {
      if (file) {
        setUploadProgress(0);
        return uploadFile(file, currentFolder.id, setUploadProgress);
      }
      return createFile({
            name: `Untitled upload ${items.length + 1}.bin`,
            size: 0,
            mimeType: "application/octet-stream",
            parentId: currentFolder.id,
          });
    },
    onSuccess: async (file) => {
      setUploadProgress(null);
      setSelectedId(file.id);
      setSelectedIds([file.id]);
      await refreshFiles();
      window.setTimeout(() => void refreshFiles(), 1500);
    },
    onError: () => setUploadProgress(null),
  });

  const deleteFileMutation = useMutation({
    mutationFn: deleteFile,
    onMutate: () => {
      setDeleteFeedback({ phase: "running", current: 0, total: 1, label: "Moving to Trash" });
    },
    onSuccess: async (_result, deletedId) => {
      if (selectedId === deletedId) setSelectedId(null);
      setSelectedIds((current) => current.filter((id) => id !== deletedId));
      setContextMenu(null);
      await refreshFiles();
      await queryClient.invalidateQueries({ queryKey: ["trash"] });
      setDeleteFeedback({ phase: "success", count: 1, label: "Moved to Trash" });
      window.setTimeout(() => setDeleteFeedback(null), 4000);
    },
    onError: (error) => {
      setDeleteFeedback({
        phase: "error",
        message: error instanceof Error ? error.message : "Could not move the item to Trash",
      });
    },
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      setDeleteFeedback({ phase: "running", current: 0, total: ids.length, label: "Moving to Trash" });
      for (let index = 0; index < ids.length; index += 1) {
        await deleteFile(ids[index]);
        setDeleteFeedback({
          phase: "running",
          current: index + 1,
          total: ids.length,
          label: "Moving to Trash",
        });
      }
    },
    onSuccess: async (_result, ids) => {
      setSelectedId(null);
      setSelectedIds([]);
      await refreshFiles();
      await queryClient.invalidateQueries({ queryKey: ["trash"] });
      setDeleteFeedback({ phase: "success", count: ids.length, label: "Moved to Trash" });
      window.setTimeout(() => setDeleteFeedback(null), 4000);
    },
    onError: (error) => {
      setDeleteFeedback({
        phase: "error",
        message: error instanceof Error ? error.message : "Could not move the selected items to Trash",
      });
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateDriveItem(id, { name }),
    onSuccess: async (updated) => {
      setRenamingId(null);
      setRenameValue("");
      setContextMenu(null);
      if (currentFolder.id === updated.id) {
        setCurrentFolder({ id: updated.id, name: updated.name });
      }
      await refreshFiles();
    },
  });

  const moveMutation = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string }) =>
      updateDriveItem(id, { parentId }),
    onSuccess: async () => {
      setDraggedItemId(null);
      setDropTargetId(null);
      setSelectedId(null);
      setSelectedIds([]);
      await refreshFiles();
    },
    onError: () => {
      setDraggedItemId(null);
      setDropTargetId(null);
    },
  });

  const syncMutation = useMutation({
    mutationFn: syncFileToTelegram,
    onSuccess: async (updated) => {
      setSelectedId(updated.id);
      setSelectedIds([updated.id]);
      setContextMenu(null);
      await refreshFiles();
    },
  });

  const bulkRestoreMutation = useMutation({
    mutationFn: (ids: string[]) => Promise.all(ids.map(restoreFromTrash)),
    onSuccess: async () => {
      setTrashSelectedIds([]);
      await queryClient.invalidateQueries({ queryKey: ["trash"] });
      await queryClient.invalidateQueries({ queryKey: ["files"] });
    },
  });

  const bulkPermanentDeleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      setDeleteFeedback({
        phase: "running",
        current: 0,
        total: ids.length,
        label: "Deleting permanently",
        indeterminate: ids.length > 3,
      });
      const result =
        ids.length === trashItems.length
          ? await emptyTrash()
          : ids.length === 1
            ? await deletePermanently(ids[0])
            : await deletePermanentlyBulk(ids);
      return { count: ids.length, telegramCleanupJobs: result.job_ids.length };
    },
    onSuccess: async ({ count, telegramCleanupJobs }) => {
      setTrashSelectedIds([]);
      void queryClient.invalidateQueries({ queryKey: ["trash"] });
      void queryClient.invalidateQueries({ queryKey: ["deletion-jobs"] });
      setDeleteFeedback({
        phase: "success",
        count: 1,
        label: telegramCleanupJobs
          ? `Deleted permanently (${telegramCleanupJobs} Telegram file${telegramCleanupJobs === 1 ? "" : "s"} cleaning up)`
          : count > 1
            ? `Deleted permanently: ${count} items`
            : "Deleted permanently",
      });
      window.setTimeout(() => setDeleteFeedback(null), 6000);
    },
    onError: (error) => {
      setDeleteFeedback({
        phase: "error",
        message: error instanceof Error ? error.message : "Could not delete the selected items",
      });
    },
  });

  const emptyTrashMutation = useMutation({
    mutationFn: emptyTrash,
    onMutate: async () => {
      const count = trashItems.length;
      await queryClient.cancelQueries({ queryKey: ["trash"] });
      const previousTrash = queryClient.getQueryData<DriveItem[]>(["trash"]);
      queryClient.setQueryData(["trash"], []);
      setTrashSelectedIds([]);
      setDeleteFeedback({
        phase: "running",
        current: 0,
        total: count,
        label: "Emptying trash",
        indeterminate: true,
      });
      return { previousTrash, count };
    },
    onSuccess: async (result) => {
      void queryClient.invalidateQueries({ queryKey: ["trash"] });
      void queryClient.invalidateQueries({ queryKey: ["deletion-jobs"] });
      const telegramCleanupJobs = result.job_ids.length;
      setDeleteFeedback({
        phase: "success",
        count: 1,
        label: telegramCleanupJobs
          ? `Trash emptied (${telegramCleanupJobs} Telegram file${telegramCleanupJobs === 1 ? "" : "s"} cleaning up)`
          : "Trash emptied",
      });
      window.setTimeout(() => setDeleteFeedback(null), 4000);
    },
    onError: (error, _variables, context) => {
      if (context?.previousTrash) {
        queryClient.setQueryData(["trash"], context.previousTrash);
      }
      setDeleteFeedback({
        phase: "error",
        message: error instanceof Error ? error.message : "Could not empty Trash",
      });
    },
  });

  const createServerFolderMutation = useMutation({
    mutationFn: () => createServerFolder(serverPath, "New folder"),
    onSuccess: async (folder) => {
      setServerSelectedPath(folder.path);
      setServerRenamingPath(folder.path);
      setServerRenameValue(folder.name);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
  });

  const uploadServerFileMutation = useMutation({
    mutationFn: (file: globalThis.File) => {
      setUploadProgress(0);
      return uploadServerFile(serverPath, file, setUploadProgress);
    },
    onSuccess: async (file) => {
      setUploadProgress(null);
      setServerSelectedPath(file.path);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
    onError: () => setUploadProgress(null),
  });

  const renameServerFileMutation = useMutation({
    mutationFn: ({ path, name }: { path: string; name: string }) =>
      updateServerFile(path, { name }),
    onSuccess: async (item) => {
      setServerRenamingPath(null);
      setServerRenameValue("");
      setServerSelectedPath(item.path);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
  });

  const moveServerFileMutation = useMutation({
    mutationFn: ({ path, parentPath }: { path: string; parentPath: string }) =>
      updateServerFile(path, { parentPath }),
    onSuccess: async () => {
      setServerDraggedPath(null);
      setServerDropTargetPath(null);
      setServerSelectedPath(null);
      setServerSelectedPaths([]);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
    onError: () => {
      setServerDraggedPath(null);
      setServerDropTargetPath(null);
    },
  });

  const deleteServerFileMutation = useMutation({
    mutationFn: deleteServerFile,
    onSuccess: async () => {
      setServerSelectedPath(null);
      setServerSelectedPaths([]);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
  });

  const bulkDeleteServerFilesMutation = useMutation({
    mutationFn: (paths: string[]) => Promise.all(paths.map(deleteServerFile)),
    onSuccess: async () => {
      setServerSelectedPath(null);
      setServerSelectedPaths([]);
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
  });

  const downloadServerFileMutation = useMutation({
    mutationFn: (item: ServerFileItem) =>
      downloadServerFile(item.path).then((download) => ({
        ...download,
        fallbackName: item.name,
      })),
    onSuccess: ({ blob, filename, fallbackName }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? fallbackName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
  });

  const saveEditorMutation = useMutation<{ revision: string } | TextFileContent, Error, EditorSave>({
    mutationFn: ({ target, payload, revision }: EditorSave) => {
      return target.source === "drive"
        ? saveDriveTextFile(target.id, {
            ...payload,
            revision,
          }).then((item) => ({ revision: item.updatedAt }))
        : saveServerTextFile(target.path, payload);
    },
    onSuccess: async (result, { target, payload }) => {
      if (target.source === "drive") await refreshFiles();
      if (target.source === "server") await queryClient.invalidateQueries({ queryKey: ["server-files"] });
      if (sameEditorTarget(editorTarget, target)) {
        setEditorDocument((current) => current && {
          ...current,
          content: payload.content,
          encoding: payload.encoding,
          newline: payload.newline,
          revision: target.source === "drive" ? result.revision : result.revision ?? current.revision,
        });
      }
      setEditorError("");
      setEditorConflict(false);
    },
    onError: (error) => {
      const status = error instanceof Error ? (error as Error & { status?: number }).status : undefined;
      if (status === 409) {
        setEditorConflict(true);
        setEditorError("This file changed elsewhere. Reload the latest version before saving again.");
        return;
      }
      setEditorConflict(false);
      setEditorError(error instanceof Error ? error.message : "Could not save the file");
    },
  });

  async function openTextEditor(target: EditorTarget) {
    if (!isEditableTextFile(target)) {
      setEditorTarget(target);
      setEditorDocument(null);
      setEditorLoading(false);
      setEditorConflict(false);
      setEditorError(
        target.size > maxEditorBytes
          ? "This file is too large for the text editor."
          : "This file type cannot be opened in the text editor.",
      );
      return;
    }
    const request = ++editorRequestRef.current;
    setEditorError("");
    setEditorConflict(false);
    setEditorTarget(target);
    setEditorDocument(null);
    setEditorLoading(true);
    try {
      const document = target.source === "drive"
        ? await readDriveTextFile(target.id)
        : await readServerTextFile(target.path);
      if (request !== editorRequestRef.current) return;
      setEditorDocument(document);
    } catch (error) {
      if (request !== editorRequestRef.current) return;
      setEditorError(error instanceof Error ? error.message : "This file cannot be opened in the editor");
    } finally {
      if (request === editorRequestRef.current) setEditorLoading(false);
    }
  }

  const copyDriveFilesToServerMutation = useMutation({
    mutationFn: (files: DriveItem[]) =>
      Promise.all(files.map((item) => copyDriveFileToServer(item.id, serverPath))),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
  });

  const importServerFileMutation = useMutation({
    mutationFn: (item: ServerFileItem) =>
      importServerFileToDrive(item.path, currentFolder.id),
    onSuccess: async (item) => {
      setSelectedId(item.id);
      setSelectedIds([item.id]);
      await queryClient.invalidateQueries({ queryKey: ["files"] });
    },
  });

  const bulkImportServerFilesMutation = useMutation({
    mutationFn: (files: ServerFileItem[]) =>
      Promise.all(files.map((item) => importServerFileToDrive(item.path, currentFolder.id))),
    onSuccess: async (items) => {
      const first = items[0];
      if (first) {
        setSelectedId(first.id);
        setSelectedIds(items.map((item) => item.id));
      }
      await queryClient.invalidateQueries({ queryKey: ["files"] });
    },
  });

  const testServerConfigMutation = useMutation({
    mutationFn: () => testServerFilesConfig(serverConfigForm),
    onSuccess: (result) => {
      setServerSetupMessage(`Connection works. Root: ${result.root}`);
    },
    onError: (error) => {
      setServerSetupMessage(error instanceof Error ? error.message : "Connection test failed.");
    },
  });

  const saveServerConfigMutation = useMutation({
    mutationFn: () => saveServerFilesConfig(serverConfigForm),
    onSuccess: async (config) => {
      setServerSetupMessage("Server Files connection saved.");
      setShowServerSetup(false);
      setServerPath("");
      setServerHistory([""]);
      setServerHistoryIndex(0);
      setServerSelectedPath(null);
      setServerSelectedPaths([]);
      setServerConfigForm((current) => ({
        mode: config.mode,
        localRoot: config.localRoot || current.localRoot,
        sftpHost: config.sftpHost || current.sftpHost,
        sftpPort: config.sftpPort || current.sftpPort,
        sftpUser: config.sftpUser || current.sftpUser,
        sftpPassword: "",
        sftpKeyPath: config.sftpKeyPath || current.sftpKeyPath,
        sftpRoot: config.sftpRoot || current.sftpRoot,
      }));
      queryClient.setQueryData(["server-files-config"], config);
      await queryClient.fetchQuery({
        queryKey: ["server-files-status"],
        queryFn: getServerFilesStatus,
        staleTime: 0,
      });
      await queryClient.fetchQuery({
        queryKey: ["server-files", ""],
        queryFn: () => listServerFiles(""),
        staleTime: 0,
      });
      await queryClient.invalidateQueries({ queryKey: ["server-files"] });
    },
    onError: (error) => {
      setServerSetupMessage(error instanceof Error ? error.message : "Could not save connection.");
    },
  });

  const downloadMutation = useMutation({
    mutationFn: (item: DriveItem) =>
      downloadFile(item.id).then((download) => ({ ...download, fallbackName: item.name })),
    onSuccess: ({ blob, filename, fallbackName }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? fallbackName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setContextMenu(null);
    },
  });

  function zipFallbackName() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    const year = now.getFullYear();
    const suffix = Math.floor(Math.random() * 0x10000)
      .toString(16)
      .padStart(4, "0");
    return `TeleDrive-${month}-${day}-${year}-${suffix}.zip`;
  }

  async function downloadSelectedFiles(files: DriveItem[]) {
    if (!files.length || isBulkDownloading) return;
    setIsBulkDownloading(true);
    try {
      const download =
        files.length === 1
          ? await downloadFile(files[0].id)
          : await downloadFilesZip(files.map((item) => item.id));
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        download.filename ?? (files.length === 1 ? files[0].name : zipFallbackName());
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } finally {
      setIsBulkDownloading(false);
    }
  }

  const authMutation = useMutation({
    mutationFn: () =>
      authMode === "register" ? register(email, password) : login(email, password),
    onSuccess: async (result) => {
      setCsrfToken(result.csrfToken);
      setSessionActive(true);
      setToken("session");
      setAuthError("");
      await queryClient.cancelQueries();
      await queryClient.invalidateQueries();
    },
    onError: (error) => {
      setAuthError(formatAuthError(error));
    },
  });

  const telegramCredentialsMutation = useMutation({
    mutationFn: () => saveTelegramCredentials(telegramApiId, telegramApiHash),
    onSuccess: async (user) => {
      setTelegramApiId("");
      setTelegramApiHash("");
      queryClient.setQueryData(["me", token], user);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["storage-status"] });
    },
  });

  const telegramSessionMutation = useMutation({
    mutationFn: saveTelegramSession,
    onSuccess: async (user) => {
      setTelegramSession("");
      queryClient.setQueryData(["me", token], user);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["storage-status"] });
    },
  });

  const telegramLoginStartMutation = useMutation({
    mutationFn: () => startTelegramLogin(telegramPhone),
    onSuccess: (result) => {
      setTelegramLoginStep(result.nextStep === "code" ? "code" : "phone");
      setTelegramLoginMessage(result.message);
      setTelegramCode("");
      setTelegramPassword("");
    },
  });

  const telegramLoginVerifyMutation = useMutation({
    mutationFn: () =>
      telegramLoginStep === "password"
        ? verifyTelegramPassword(telegramPassword)
        : verifyTelegramLogin(telegramCode, telegramPassword),
    onSuccess: async (result) => {
      setTelegramLoginMessage(result.message);
      if (result.nextStep === "password") {
        setTelegramLoginStep("password");
        setTelegramPassword("");
        return;
      }
      if (result.nextStep === "done" && result.user) {
        setTelegramLoginStep("done");
        setTelegramCode("");
        setTelegramPassword("");
        queryClient.setQueryData(["me", token], result.user);
        await queryClient.invalidateQueries({ queryKey: ["me"] });
        await queryClient.invalidateQueries({ queryKey: ["storage-status"] });
      }
    },
  });
  const accountMutation = useMutation({
    mutationFn: () =>
      updateAccount({
        currentPassword,
        email:
          accountEmail.trim() && accountEmail.trim() !== meQuery.data?.email
            ? accountEmail.trim()
            : undefined,
        newPassword: newPassword || undefined,
      }),
    onSuccess: async (user) => {
      queryClient.setQueryData(["me", token], user);
      setAccountEmail(user.email);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setAccountMessage("Account settings saved.");
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: () => setAccountMessage("Account update failed. Check your current password."),
  });
  const registrationSettingsMutation = useMutation({
    mutationFn: updateRegistrationSettings,
    onSuccess: async (registrationEnabled) => {
      queryClient.setQueryData(["registration-settings"], registrationEnabled);
      await queryClient.invalidateQueries({ queryKey: ["registration-settings"] });
    },
  });
  const createManifestMutation = useMutation({
    mutationFn: createRecoveryManifest,
    onSuccess: () => setRecoveryMessage("Encrypted recovery manifest saved to Telegram."),
    onError: (error) => setRecoveryMessage(error instanceof Error ? error.message : "Could not create a manifest."),
  });
  const restoreManifestMutation = useMutation({
    mutationFn: restoreRecoveryManifest,
    onSuccess: async ({ restored }) => {
      setRecoveryMessage(`Restored ${restored} missing item${restored === 1 ? "" : "s"} from Telegram.`);
      await queryClient.invalidateQueries({ queryKey: ["files"] });
    },
    onError: (error) => setRecoveryMessage(error instanceof Error ? error.message : "Could not restore the manifest."),
  });
  const importTelegramRecoveryMutation = useMutation({
    mutationFn: importTelegramRecovery,
    onSuccess: async ({ items_processed }) => {
      setRecoveryMessage(`Imported ${items_processed} Telegram document${items_processed === 1 ? "" : "s"}.`);
      await queryClient.invalidateQueries({ queryKey: ["files"] });
    },
    onError: (error) => setRecoveryMessage(error instanceof Error ? error.message : "Could not import Telegram documents."),
  });
  const cleanupManifestsMutation = useMutation({
    mutationFn: cleanupStaleManifests,
    onSuccess: async ({ removed }) => {
      setRecoveryMessage(
        removed
          ? `Removed ${removed} old manifest file${removed === 1 ? "" : "s"} from Telegram storage.`
          : "No extra manifest files found in Telegram storage.",
      );
      await queryClient.invalidateQueries({ queryKey: ["deletion-jobs"] });
    },
    onError: (error) =>
      setRecoveryMessage(formatApiError(error, "Could not clean up manifest files.")),
  });
  const purgeChannelMutation = useMutation({
    mutationFn: purgeChannelStorage,
    onSuccess: async ({ removed }) => {
      setRecoveryMessage(
        removed
          ? `Removed ${removed} file${removed === 1 ? "" : "s"} from Telegram storage channel.`
          : "Telegram storage channel is already empty.",
      );
      await queryClient.invalidateQueries({ queryKey: ["deletion-jobs"] });
    },
    onError: (error) =>
      setRecoveryMessage(formatApiError(error, "Could not clean up Telegram storage channel.")),
  });
  const retryDeletionJobsMutation = useMutation({
    mutationFn: retryDeletionJobs,
    onSuccess: async ({ attempted, failed, completed }) => {
      setRecoveryMessage(
        failed
          ? `Telegram cleanup retried ${attempted} file(s): ${completed} removed, ${failed} still failing.`
          : `Telegram cleanup removed ${completed} file${completed === 1 ? "" : "s"} from storage.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["deletion-jobs"] });
    },
    onError: (error) =>
      setRecoveryMessage(formatApiError(error, "Could not retry Telegram cleanup.")),
  });
  const actionError =
    createFileMutation.error ??
    syncMutation.error ??
    renameMutation.error ??
    moveMutation.error ??
    downloadMutation.error ??
    createServerFolderMutation.error ??
    uploadServerFileMutation.error ??
    renameServerFileMutation.error ??
    moveServerFileMutation.error ??
    deleteServerFileMutation.error ??
    bulkDeleteServerFilesMutation.error ??
    downloadServerFileMutation.error ??
    copyDriveFilesToServerMutation.error ??
    importServerFileMutation.error ??
    bulkImportServerFilesMutation.error ??
    testServerConfigMutation.error ??
    saveServerConfigMutation.error ??
    bulkRestoreMutation.error ??
    telegramCredentialsMutation.error ??
    telegramLoginStartMutation.error ??
    telegramLoginVerifyMutation.error ??
    telegramSessionMutation.error ??
    accountMutation.error;
  const actionErrorMessage = actionError instanceof Error ? actionError.message : "";
  const isDriveDeleting = deleteFileMutation.isPending || bulkDeleteMutation.isPending;
  const isTrashDeleting =
    bulkPermanentDeleteMutation.isPending || emptyTrashMutation.isPending;

  function renderDeleteFeedback() {
    if (!deleteFeedback) return null;
    if (deleteFeedback.phase === "running") {
      const progressLabel = deleteFeedback.indeterminate
        ? deleteFeedback.total > 0
          ? `${deleteFeedback.label} (${deleteFeedback.total} items)...`
          : `${deleteFeedback.label}...`
        : `${deleteFeedback.label} ${deleteFeedback.current}/${deleteFeedback.total}...`;
      return (
        <span className="status-detail delete-feedback">
          <RefreshCw size={14} className="spinning" />
          {progressLabel}
        </span>
      );
    }
    if (deleteFeedback.phase === "success") {
      const detail =
        deleteFeedback.count > 1
          ? `${deleteFeedback.label}: ${deleteFeedback.count} items`
          : deleteFeedback.label;
      return (
        <span className="status-success">
          <CheckCircle2 size={14} />
          {detail}
        </span>
      );
    }
    return <span className="status-error">{deleteFeedback.message}</span>;
  }

  function logout() {
    void endSession();
    setSessionActive(false);
    setToken("");
    setSelectedId(null);
    setSelectedIds([]);
    setDeleteFeedback(null);
    void queryClient.clear();
  }

  function startRename(item: DriveItem) {
    setSelectedId(item.id);
    setSelectedIds([item.id]);
    setRenamingId(item.id);
    setRenameValue(item.name);
    setContextMenu(null);
  }

  function submitRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renamingId || !renameValue.trim()) {
      setRenamingId(null);
      return;
    }
    const id = renamingId;
    setRenamingId(null);
    renameMutation.mutate({ id, name: renameValue.trim() });
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (draggedItemId) return;
    const droppedFiles = [...event.dataTransfer.files];
    droppedFiles.forEach((file) => createFileMutation.mutate(file));
  }

  function selectOnly(item: DriveItem) {
    setSelectedId(item.id);
    setSelectedIds([item.id]);
  }

  function handleDriveItemClick(item: DriveItem, event: MouseEvent<HTMLElement>) {
    const index = filteredItems.findIndex((entry) => entry.id === item.id);
    if (event.ctrlKey || event.metaKey) {
      toggleItemSelection(item);
      if (index >= 0) lastDriveSelectionIndexRef.current = index;
      return;
    }
    if (
      event.shiftKey &&
      lastDriveSelectionIndexRef.current !== null &&
      index >= 0
    ) {
      const anchor = lastDriveSelectionIndexRef.current;
      const start = Math.min(anchor, index);
      const end = Math.max(anchor, index);
      const rangeIds = filteredItems.slice(start, end + 1).map((entry) => entry.id);
      setSelectedIds(rangeIds);
      setSelectedId(item.id);
      return;
    }
    selectOnly(item);
    if (index >= 0) lastDriveSelectionIndexRef.current = index;
  }

  function requestBulkDelete() {
    if (!selectedIds.length || isDriveDeleting) return;
    if (
      selectedIds.length > 1 &&
      !window.confirm(`Move ${selectedIds.length} selected items to Trash?`)
    ) {
      return;
    }
    bulkDeleteMutation.mutate(selectedIds);
  }

  function toggleItemSelection(item: DriveItem) {
    const index = filteredItems.findIndex((entry) => entry.id === item.id);
    setSelectedIds((current) => {
      const next = current.includes(item.id)
        ? current.filter((id) => id !== item.id)
        : [...current, item.id];
      setSelectedId(next.includes(item.id) ? item.id : (next[next.length - 1] ?? null));
      return next;
    });
    if (index >= 0) lastDriveSelectionIndexRef.current = index;
  }

  function toggleTrashSelection(item: DriveItem) {
    setTrashSelectedIds((current) => {
      const next = current.includes(item.id)
        ? current.filter((id) => id !== item.id)
        : [...current, item.id];
      return next;
    });
  }

  function startItemDrag(event: DragEvent<HTMLElement>, item: DriveItem) {
    setDraggedItemId(item.id);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-teledrive-item", item.id);
  }

  function moveItemToFolder(event: DragEvent<HTMLElement>, folder: DriveItem) {
    const itemId =
      event.dataTransfer.getData("application/x-teledrive-item") || draggedItemId;
    if (!itemId) return;
    event.preventDefault();
    event.stopPropagation();
    setDropTargetId(null);
    if (itemId === folder.id || moveMutation.isPending) return;
    moveMutation.mutate({ id: itemId, parentId: folder.id });
  }

  function markFolderDropTarget(event: DragEvent<HTMLElement>, folder: DriveItem) {
    if (!draggedItemId || draggedItemId === folder.id) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDropTargetId(folder.id);
  }

  function triggerUpload() {
    fileInputRef.current?.click();
  }

  function openDownload(item: DriveItem) {
    if (item.kind !== "file") return;
    downloadMutation.mutate(item);
  }

  function openRoot() {
    setSidePanel("files");
    navigateTo(path[0], [path[0]]);
  }

  async function refreshStatus() {
    if (isRefreshingStatus) return;
    setIsRefreshingStatus(true);
    try {
      await refreshFiles();
      await queryClient.invalidateQueries({ queryKey: ["update-status"] });
      setStatusRefreshedAt(new Date());
    } finally {
      setIsRefreshingStatus(false);
    }
  }

  function handleTreeAction(event: MouseEvent<HTMLButtonElement>, action: () => void) {
    event.stopPropagation();
    setContextMenu(null);
    setRenamingId(null);
    action();
  }

  function openServerFiles() {
    setSidePanel("server");
    setServerSelectedPath(null);
    void queryClient.fetchQuery({
      queryKey: ["server-files", serverPath],
      queryFn: () => listServerFiles(serverPath),
      staleTime: 0,
    });
  }

  function navigateServerTo(nextPath: string, pushHistory = true) {
    setServerPath(nextPath);
    setServerSelectedPath(null);
    setServerSelectedPaths([]);
    setServerRenamingPath(null);
    setServerDropTargetPath(null);
    if (!pushHistory) return;
    const trimmedHistory = serverHistory.slice(0, serverHistoryIndex + 1);
    const lastPath = trimmedHistory[trimmedHistory.length - 1];
    if (lastPath !== nextPath) {
      setServerHistory([...trimmedHistory, nextPath]);
      setServerHistoryIndex(trimmedHistory.length);
    }
  }

  function openServerFolder(item: ServerFileItem) {
    if (item.kind !== "folder") return;
    navigateServerTo(item.path);
  }

  function goServerUp() {
    navigateServerTo(serverParentPath);
  }

  function goServerBack() {
    if (!canGoServerBack) return;
    const nextIndex = serverHistoryIndex - 1;
    setServerHistoryIndex(nextIndex);
    navigateServerTo(serverHistory[nextIndex], false);
  }

  function goServerForward() {
    if (!canGoServerForward) return;
    const nextIndex = serverHistoryIndex + 1;
    setServerHistoryIndex(nextIndex);
    navigateServerTo(serverHistory[nextIndex], false);
  }

  function startServerRename(item: ServerFileItem) {
    setServerSelectedPath(item.path);
    setServerSelectedPaths([item.path]);
    setServerRenamingPath(item.path);
    setServerRenameValue(item.name);
  }

  function submitServerRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!serverRenamingPath || !serverRenameValue.trim()) {
      setServerRenamingPath(null);
      return;
    }
    renameServerFileMutation.mutate({
      path: serverRenamingPath,
      name: serverRenameValue.trim(),
    });
  }

  function triggerServerUpload() {
    serverFileInputRef.current?.click();
  }

  function downloadServerItem(item: ServerFileItem | undefined) {
    if (!item || item.kind !== "file") return;
    downloadServerFileMutation.mutate(item);
  }

  function selectOnlyServerItem(item: ServerFileItem) {
    setServerSelectedPath(item.path);
    setServerSelectedPaths([item.path]);
  }

  function toggleServerItemSelection(item: ServerFileItem) {
    setServerSelectedPaths((current) => {
      const next = current.includes(item.path)
        ? current.filter((path) => path !== item.path)
        : [...current, item.path];
      setServerSelectedPath(next.includes(item.path) ? item.path : (next[next.length - 1] ?? null));
      return next;
    });
  }

  async function downloadSelectedServerFiles(files: ServerFileItem[]) {
    for (const item of files) {
      const { blob, filename } = await downloadServerFile(item.path);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? item.name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    }
  }

  function startServerDrag(event: DragEvent<HTMLElement>, item: ServerFileItem) {
    setServerDraggedPath(item.path);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-teledrive-server-path", item.path);
  }

  function markServerDropTarget(event: DragEvent<HTMLElement>, item: ServerFileItem) {
    if (!serverDraggedPath || item.kind !== "folder" || serverDraggedPath === item.path) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setServerDropTargetPath(item.path);
  }

  function moveServerItemToFolder(event: DragEvent<HTMLElement>, folder: ServerFileItem) {
    const sourcePath =
      event.dataTransfer.getData("application/x-teledrive-server-path") || serverDraggedPath;
    if (!sourcePath || folder.kind !== "folder") return;
    event.preventDefault();
    event.stopPropagation();
    setServerDropTargetPath(null);
    if (sourcePath === folder.path || moveServerFileMutation.isPending) return;
    moveServerFileMutation.mutate({ path: sourcePath, parentPath: folder.path });
  }

  function handleServerDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const sourcePath =
      event.dataTransfer.getData("application/x-teledrive-server-path") || serverDraggedPath;
    if (sourcePath) {
      if (parentServerPath(sourcePath) !== serverPath) {
        moveServerFileMutation.mutate({ path: sourcePath, parentPath: serverPath });
      }
      return;
    }
    [...event.dataTransfer.files].forEach((file) => uploadServerFileMutation.mutate(file));
  }

  const columns = useMemo(
    () => [
      columnHelper.accessor("name", {
        header: () => (
          <label className="table-select-name">
            <input
              type="checkbox"
              checked={allVisibleDriveSelected}
              onChange={() => {
                if (allVisibleDriveSelected) {
                  setSelectedIds((current) =>
                    current.filter((id) => !visibleDriveItemIds.includes(id)),
                  );
                  setSelectedId(null);
                } else {
                  setSelectedIds((current) =>
                    Array.from(new Set([...current, ...visibleDriveItemIds])),
                  );
                  setSelectedId(filteredItems[0]?.id ?? null);
                }
              }}
            />
            Name
          </label>
        ),
        cell: ({ row, getValue }) => (
          <span className="file-name">
            <input
              className="row-checkbox"
              type="checkbox"
              checked={selectedIds.includes(row.original.id)}
              aria-label={`Select ${row.original.name}`}
              onChange={() => toggleItemSelection(row.original)}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
            />
            <span className="file-icon">
              {row.original.kind === "folder" ? <Folder size={18} /> : <FileIcon size={18} />}
            </span>
            {renamingId === row.original.id ? (
              <form className="rename-form" onSubmit={submitRename}>
                <input
                  autoFocus
                  value={renameValue}
                  onBlur={(event) => event.currentTarget.form?.requestSubmit()}
                  onChange={(event) => setRenameValue(event.target.value)}
                  onClick={(event) => event.stopPropagation()}
                  onDoubleClick={(event) => event.stopPropagation()}
                />
              </form>
            ) : (
              getValue()
            )}
          </span>
        ),
      }),
      columnHelper.accessor("size", {
        header: "Size",
        cell: ({ getValue }) => formatBytes(getValue()),
      }),
      columnHelper.accessor("mimeType", {
        header: "Type",
        cell: ({ row }) => formatFileType(row.original),
      }),
      columnHelper.accessor("syncStatus", {
        header: "Sync",
        cell: ({ row, getValue }) =>
          row.original.kind === "folder" ? "-" : (
            <span className={`sync-pill ${getValue()}`}>{getValue()}</span>
          ),
      }),
      columnHelper.accessor("updatedAt", {
        header: "Date modified",
        cell: ({ getValue }) => new Date(getValue()).toLocaleDateString(),
      }),
      columnHelper.display({
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <span className="row-actions">
            <button
              type="button"
              className="icon-button row-actions-button"
              aria-label={`Actions for ${row.original.name}`}
              onClick={(event: MouseEvent<HTMLButtonElement>) => {
                event.preventDefault();
                event.stopPropagation();
                setContextMenu({
                  x: event.clientX,
                  y: event.clientY,
                  item: row.original,
                });
              }}
            >
              <MoreHorizontal size={16} aria-hidden="true" />
            </button>
          </span>
        ),
      }),
    ],
    [allVisibleDriveSelected, filteredItems, renamingId, renameValue, selectedIds, visibleDriveItemIds],
  );

  const table = useReactTable({
    data: filteredItems,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (bootstrapping || !token || meQuery.isError) {
    return (
      <AuthScreen
        bootstrapping={bootstrapping}
        authMode={authMode}
        onAuthModeChange={setAuthMode}
        email={email}
        onEmailChange={setEmail}
        password={password}
        onPasswordChange={setPassword}
        authError={authError}
        isSubmitting={authMutation.isPending}
        onSubmit={() => authMutation.mutate()}
      />
    );
  }

  return (
    <main className="app-shell" onClick={() => setContextMenu(null)}>
      <aside className="sidebar" aria-label="Navigation pane">
        <div className="brand">
          <div className="brand-mark">
            <Cloud size={22} />
          </div>
          <div>
            <strong>TeleDrive</strong>
            <span>Telegram private storage</span>
          </div>
        </div>

        <nav className="nav-tree">
          <p className="tree-label">Quick access</p>
          <button
            type="button"
            data-testid="nav-home"
            className={`tree-item ${sidePanel === "files" && currentFolder.id === null ? "active" : ""}`}
            onClick={(event) => handleTreeAction(event, openRoot)}
          >
            <Home size={16} />
            Home
          </button>
          <button
            type="button"
            data-testid="nav-storage"
            className={`tree-item ${sidePanel === "files" && currentFolder.id === null ? "active" : ""}`}
            onClick={(event) => handleTreeAction(event, openRoot)}
          >
            <HardDrive size={16} />
            TeleDrive Storage
          </button>
          {rootItems
            .filter((item) => item.kind === "folder")
            .map((folder) => (
              <button
                type="button"
                className={`tree-item child ${
                  sidePanel === "files" && currentFolder.id === folder.id ? "active" : ""
                } ${dropTargetId === folder.id ? "drop-target" : ""}`}
                key={folder.id}
                onClick={() => openRootFolder(folder)}
                onDragOver={(event) => markFolderDropTarget(event, folder)}
                onDragLeave={() => setDropTargetId(null)}
                onDrop={(event) => moveItemToFolder(event, folder)}
              >
                <Folder size={16} />
                {folder.name}
              </button>
            ))}
          <button
            type="button"
            data-testid="nav-trash"
            className={`tree-item ${sidePanel === "trash" ? "active" : ""}`}
            onClick={(event) =>
              handleTreeAction(event, () => {
                setSidePanel("trash");
                void queryClient.fetchQuery({
                  queryKey: ["trash"],
                  queryFn: listTrash,
                  staleTime: 0,
                });
              })
            }
          >
            <Trash2 size={16} />
            Trash Bin
          </button>
          {meQuery.data?.isOperator && (
            <button
              type="button"
              data-testid="nav-server-files"
              className={`tree-item ${sidePanel === "server" ? "active" : ""}`}
              onClick={(event) => handleTreeAction(event, openServerFiles)}
            >
              <Server size={16} />
              Server Files
            </button>
          )}
          <p className="tree-label">System</p>
          <button
            type="button"
            data-testid="nav-access"
            className={`tree-item ${sidePanel === "access" ? "active" : ""}`}
            onClick={(event) => handleTreeAction(event, () => setSidePanel("access"))}
          >
            <Shield size={16} />
            Access
          </button>
          <button
            type="button"
            data-testid="nav-account"
            className={`tree-item ${sidePanel === "account" ? "active" : ""}`}
            onClick={(event) =>
              handleTreeAction(event, () => {
                setAccountEmail(meQuery.data?.email ?? "");
                setAccountMessage("");
                setSidePanel("account");
              })
            }
          >
            <UserRound size={16} />
            Account settings
          </button>
          <button
            type="button"
            data-testid="nav-telegram-setup"
            className={`tree-item ${sidePanel === "setup" ? "active" : ""}`}
            onClick={(event) => handleTreeAction(event, () => setSidePanel("setup"))}
          >
            <KeyRound size={16} />
            Telegram setup
          </button>
          <button
            type="button"
            data-testid="nav-api-status"
            className={`tree-item ${sidePanel === "api" ? "active" : ""}`}
            onClick={(event) => handleTreeAction(event, () => setSidePanel("api"))}
          >
            <Info size={16} />
            API status
          </button>
        </nav>

        <section className="storage-summary">
          <div className="storage-icon">
            <Lock size={18} />
          </div>
          <div>
            <strong>{status?.channelName ?? "TeleDrive Storage"}</strong>
            <small>{status?.ready ? "Connected" : "Session needed"}</small>
          </div>
        </section>
        <section className="session-panel">
          <strong>{meQuery.data?.email ?? "Signed in"}</strong>
          <button
            className="tool-button"
            onClick={() => setSidePanel("setup")}
          >
            <KeyRound size={15} />
            Telegram setup
          </button>
          <button className="tool-button" onClick={logout}>
            <LogOut size={15} />
            Sign out
          </button>
        </section>
      </aside>

      <section className="workspace">
        <header className="explorer-top">
          <div className="window-title">
            <FolderOpen size={16} />
            <span>{currentFolder.name}</span>
          </div>
          <div className="toolbar" aria-label="Command bar">
            <button className="tool-button command-new" onClick={() => createFolderMutation.mutate()}>
              <FolderPlus size={16} />
              New
            </button>
            <button className="tool-button command-upload primary" onClick={triggerUpload}>
              <UploadCloud size={16} />
              Upload
            </button>
            <input
              ref={fileInputRef}
              className="file-input"
              type="file"
              multiple
              onChange={(event) => {
                [...(event.target.files ?? [])].forEach((file) =>
                  createFileMutation.mutate(file),
                );
                event.target.value = "";
              }}
            />
            <span className="toolbar-separator" />
            <label className="selection-control">
              <input
                type="checkbox"
                checked={allVisibleDriveSelected}
                onChange={() => {
                  if (allVisibleDriveSelected) {
                    setSelectedIds((current) =>
                      current.filter((id) => !visibleDriveItemIds.includes(id)),
                    );
                    setSelectedId(null);
                  } else {
                    setSelectedIds((current) =>
                      Array.from(new Set([...current, ...visibleDriveItemIds])),
                    );
                    setSelectedId(filteredItems[0]?.id ?? null);
                  }
                }}
              />
              Select all
            </label>
            <button
              className="tool-button command-edit"
              disabled={!selectedItem || selectedIds.length !== 1}
              onClick={() => selectedItem && startRename(selectedItem)}
            >
              <Edit3 size={16} />
              Rename
            </button>
            <button
              className="tool-button command-delete danger"
              disabled={!selectedIds.length || isDriveDeleting}
              title={selectedIds.length ? undefined : "Select items with checkboxes, Ctrl+click, or Shift+click"}
              onClick={requestBulkDelete}
            >
              <Trash2 size={16} className={isDriveDeleting ? "spinning" : ""} />
              {isDriveDeleting
                ? "Deleting..."
                : selectedIds.length > 1
                  ? `Delete (${selectedIds.length})`
                  : "Delete"}
            </button>
            <button
              className="tool-button command-download"
              disabled={!selectedFiles.length || isBulkDownloading}
              onClick={() => void downloadSelectedFiles(selectedFiles)}
            >
              <Download size={16} />
              {isBulkDownloading
                ? "Downloading..."
                : selectedFiles.length > 1
                  ? `Download (${selectedFiles.length})`
                  : "Download"}
            </button>
            <button
              className="tool-button command-server"
              disabled={!meQuery.data?.isOperator || !selectedFiles.length || copyDriveFilesToServerMutation.isPending}
              onClick={() => copyDriveFilesToServerMutation.mutate(selectedFiles)}
            >
              <Server size={16} />
              {copyDriveFilesToServerMutation.isPending
                ? "Copying..."
                : selectedFiles.length > 1
                  ? `Copy to Server (${selectedFiles.length})`
                  : "Copy to Server"}
            </button>
            <button
              className="tool-button command-sync"
              disabled={selectedIds.length !== 1 || !selectedItem || selectedItem.kind !== "file"}
              onClick={() => selectedItem && syncMutation.mutate(selectedItem.id)}
            >
              <CloudUpload size={16} />
              Sync
            </button>
            <span className="toolbar-separator" />
            <label className="tool-select">
              <LayoutList size={16} />
              <span>View</span>
              <select
                value={viewMode}
                onChange={(event) => setViewMode(event.target.value as ViewMode)}
              >
                <option value="details">Details</option>
                <option value="compact">Compact</option>
              </select>
            </label>
            <label className="tool-select">
              <SlidersHorizontal size={16} />
              <span>Sort</span>
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as SortMode)}
              >
                <option value="name">{sortLabels.name}</option>
                <option value="updated">{sortLabels.updated}</option>
                <option value="size">{sortLabels.size}</option>
                <option value="sync">{sortLabels.sync}</option>
              </select>
            </label>
            <button className={`tool-button command-details ${showDetails ? "active" : ""}`} onClick={() => setShowDetails(!showDetails)}>
              <PanelRight size={16} />
              {showDetails ? "Hide details" : "Show details"}
            </button>
            <span className="toolbar-spacer" />
            <button
              className="icon-button command-refresh"
              onClick={() => void refreshFiles()}
              title="Refresh"
              aria-label="Refresh file list"
            >
              <RefreshCw size={16} aria-hidden="true" />
            </button>
          </div>
        </header>

        <section className="address-row">
          <div className="history-buttons">
            <button className="icon-button" disabled={!canGoBack} onClick={goBack} title="Back" aria-label="Go back">
              <ArrowLeft size={16} aria-hidden="true" />
            </button>
            <button
              className="icon-button"
              disabled={!canGoForward}
              onClick={goForward}
              title="Forward"
              aria-label="Go forward"
            >
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <button className="icon-button" disabled={!canGoUp} onClick={goUp} title="Up" aria-label="Go up one folder">
              <ChevronDown className="up-icon" size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="address-bar" aria-label="Address">
            {path.map((entry, index) => (
              <span className="crumb-group" key={`${entry.id ?? "root"}-${index}`}>
                {index === 0 ? <Home size={15} /> : <ChevronRight size={14} />}
                <button
                  className="crumb"
                  onClick={() => navigateTo(entry, path.slice(0, index + 1))}
                >
                  {entry.name}
                </button>
              </span>
            ))}
          </div>
          <label className="search">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${currentFolder.name}`}
            />
          </label>
        </section>

        <section className="status-strip">
          <div className="status-left">
            <span className={status?.ready ? "status ready" : "status waiting"}>
              {status?.ready ? <CheckCircle2 size={16} /> : <Cloud size={16} />}
              {status?.ready ? "Telegram storage ready" : "Telegram session needed"}
            </span>
            <span className="status-detail">
              {status?.details ?? "Checking Telegram storage..."}
            </span>
            {updateStatus?.updateAvailable && (
              <a
                className="update-pill"
                href={updateStatus.releaseUrl ?? "#"}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => {
                  if (!updateStatus.releaseUrl) event.preventDefault();
                }}
              >
                <RefreshCw size={14} />
                Update available {updateStatus.latestVersion}
                {updateStatus.releaseUrl && <ExternalLink size={13} />}
              </a>
            )}
            {actionErrorMessage && <span className="status-error">{actionErrorMessage}</span>}
            {renderDeleteFeedback()}
            {uploadProgress !== null && <span className="status-detail">Uploading {uploadProgress}%</span>}
          </div>
          <div className="metrics">
            <span>{items.length} items</span>
            <span>{formatBytes(totalSize)} tracked</span>
            <span>{currentFolder.name}</span>
          </div>
        </section>

        {sidePanel !== "files" ? (
          <section className="system-panel">
            {sidePanel === "server" && (
              <>
                <div className="system-heading">
                  <Server size={22} />
                  <div>
                    <h2>Server Files</h2>
                    <p>
                      {serverStatus?.details ?? "Browse files from the configured VPS folder."}
                    </p>
                  </div>
                </div>
                <div className="server-setup-toggle">
                  <span>
                    {serverConfigQuery.data?.source === "account"
                      ? "Connection saved in this account"
                      : "Using default server configuration"}
                  </span>
                  <button
                    className="tool-button"
                    type="button"
                    onClick={() => {
                      setShowServerSetup(!showServerSetup);
                      setServerSetupMessage("");
                    }}
                  >
                    <SlidersHorizontal size={16} />
                    {showServerSetup ? "Hide settings" : "Connection settings"}
                  </button>
                </div>
                {showServerSetup && (
                  <form
                    className="server-setup-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      saveServerConfigMutation.mutate();
                    }}
                  >
                    <div className="mode-options">
                      <label className={serverConfigForm.mode === "sftp" ? "selected" : ""}>
                        <input
                          type="radio"
                          name="server-mode"
                          checked={serverConfigForm.mode === "sftp"}
                          onChange={() =>
                            setServerConfigForm((current) => ({ ...current, mode: "sftp" }))
                          }
                        />
                        <span>
                          <strong>VPS via SSH</strong>
                          <small>TeleDrive runs locally and opens files on your VPS.</small>
                        </span>
                      </label>
                      <label className={serverConfigForm.mode === "local" ? "selected" : ""}>
                        <input
                          type="radio"
                          name="server-mode"
                          checked={serverConfigForm.mode === "local"}
                          onChange={() =>
                            setServerConfigForm((current) => ({ ...current, mode: "local" }))
                          }
                        />
                        <span>
                          <strong>Local server folder</strong>
                          <small>TeleDrive is installed on the VPS and reads a local folder.</small>
                        </span>
                      </label>
                    </div>
                    {serverConfigForm.mode === "sftp" ? (
                      <div className="server-form-grid">
                        <label>
                          VPS IP / Host
                          <input
                            value={serverConfigForm.sftpHost}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpHost: event.target.value,
                              }))
                            }
                            placeholder="example.com"
                          />
                        </label>
                        <label>
                          SSH port
                          <input
                            type="number"
                            min={1}
                            max={65535}
                            value={serverConfigForm.sftpPort}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpPort: Number(event.target.value) || 22,
                              }))
                            }
                          />
                        </label>
                        <label>
                          Username
                          <input
                            value={serverConfigForm.sftpUser}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpUser: event.target.value,
                              }))
                            }
                            placeholder="deploy"
                          />
                        </label>
                        <label>
                          Root folder on VPS
                          <input
                            value={serverConfigForm.sftpRoot}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpRoot: event.target.value,
                              }))
                            }
                            placeholder="/home/deploy"
                          />
                        </label>
                        <label className="wide-field">
                          SSH key path
                          <input
                            value={serverConfigForm.sftpKeyPath}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpKeyPath: event.target.value,
                              }))
                            }
                            placeholder="/home/your-user/.ssh/id_rsa"
                          />
                        </label>
                        <label className="wide-field">
                          Password <span>Optional, leave blank when using SSH key</span>
                          <input
                            type="password"
                            value={serverConfigForm.sftpPassword}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                sftpPassword: event.target.value,
                              }))
                            }
                            placeholder={
                              serverConfigQuery.data?.hasSftpPassword
                                ? "Password already saved"
                                : "Optional"
                            }
                          />
                        </label>
                      </div>
                    ) : (
                      <div className="server-form-grid">
                        <label className="wide-field">
                          Server folder
                          <input
                            value={serverConfigForm.localRoot}
                            onChange={(event) =>
                              setServerConfigForm((current) => ({
                                ...current,
                                localRoot: event.target.value,
                              }))
                            }
                            placeholder="/home/admin"
                          />
                        </label>
                      </div>
                    )}
                    <div className="server-setup-actions">
                      <button
                        className="tool-button"
                        type="button"
                        disabled={testServerConfigMutation.isPending}
                        onClick={() => testServerConfigMutation.mutate()}
                      >
                        <RefreshCw
                          className={testServerConfigMutation.isPending ? "spinning" : ""}
                          size={16}
                        />
                        {testServerConfigMutation.isPending ? "Testing..." : "Test connection"}
                      </button>
                      <button
                        className="tool-button primary"
                        type="submit"
                        disabled={saveServerConfigMutation.isPending}
                      >
                        {saveServerConfigMutation.isPending ? "Saving..." : "Save connection"}
                      </button>
                      {serverSetupMessage && <p>{serverSetupMessage}</p>}
                    </div>
                  </form>
                )}
                <div className="server-actions">
                  <button className="button system-back command-back" onClick={openRoot}>
                    <ArrowLeft size={16} />
                    Back to My Drive
                  </button>
                  <span className="server-navigation" aria-label="Server folder navigation">
                    <button
                      className="icon-button"
                      disabled={!canGoServerBack}
                      onClick={goServerBack}
                      title="Back"
                    >
                      <ArrowLeft size={16} />
                    </button>
                    <button
                      className="icon-button"
                      disabled={!canGoServerForward}
                      onClick={goServerForward}
                      title="Forward"
                    >
                      <ArrowRight size={16} />
                    </button>
                    <button
                      className="icon-button"
                      disabled={!canGoServerUp}
                      onClick={goServerUp}
                      title="Up"
                    >
                      <ChevronDown className="up-icon" size={16} />
                    </button>
                  </span>
                  <button
                    className="tool-button command-new"
                    onClick={() => createServerFolderMutation.mutate()}
                    disabled={createServerFolderMutation.isPending}
                  >
                    <FolderPlus size={16} />
                    New folder
                  </button>
                  <button className="tool-button command-upload primary" onClick={triggerServerUpload}>
                    <UploadCloud size={16} />
                    Upload
                  </button>
                  <input
                    ref={serverFileInputRef}
                    className="file-input"
                    type="file"
                    multiple
                    onChange={(event) => {
                      [...(event.target.files ?? [])].forEach((file) =>
                        uploadServerFileMutation.mutate(file),
                      );
                      event.target.value = "";
                    }}
                  />
                  <label className="selection-control server-select-all">
                    <input
                      type="checkbox"
                      checked={allServerItemsSelected}
                      onChange={() => {
                        if (allServerItemsSelected) {
                          setServerSelectedPaths([]);
                          setServerSelectedPath(null);
                        } else {
                          setServerSelectedPaths(serverItems.map((item) => item.path));
                          setServerSelectedPath(serverItems[0]?.path ?? null);
                        }
                      }}
                    />
                    Select all
                  </label>
                  <button
                    className="tool-button command-edit"
                    disabled={!serverSelectedItem || serverSelectedItem.kind !== "file" || !isEditableTextFile(serverSelectedItem) || serverSelectedPaths.length !== 1}
                    onClick={() => serverSelectedItem && void openTextEditor({
                      source: "server",
                      path: serverSelectedItem.path,
                      name: serverSelectedItem.name,
                      size: serverSelectedItem.size,
                    })}
                  >
                    <Edit3 size={16} />
                    Edit text
                  </button>
                  <button
                    className="tool-button command-edit"
                    disabled={!serverSelectedItem || serverSelectedPaths.length !== 1}
                    onClick={() => serverSelectedItem && startServerRename(serverSelectedItem)}
                  >
                    <Edit3 size={16} />
                    Rename
                  </button>
                  <button
                    className="tool-button command-download"
                    disabled={!serverSelectedFiles.length || downloadServerFileMutation.isPending}
                    onClick={() => void downloadSelectedServerFiles(serverSelectedFiles)}
                  >
                    <Download size={16} />
                    {serverSelectedFiles.length > 1
                      ? `Download (${serverSelectedFiles.length})`
                      : "Download"}
                  </button>
                  <button
                    className="tool-button command-sync"
                    disabled={
                      !serverSelectedFiles.length ||
                      bulkImportServerFilesMutation.isPending
                    }
                    onClick={() => bulkImportServerFilesMutation.mutate(serverSelectedFiles)}
                  >
                    <CloudUpload size={16} />
                    {bulkImportServerFilesMutation.isPending
                      ? "Importing..."
                      : serverSelectedFiles.length > 1
                        ? `Import (${serverSelectedFiles.length})`
                        : "Import to Drive"}
                  </button>
                  <button
                    className="tool-button command-delete danger"
                    disabled={!serverSelectedPaths.length || bulkDeleteServerFilesMutation.isPending}
                    onClick={() => {
                      if (
                        serverSelectedPaths.length &&
                        window.confirm(
                          `Delete ${serverSelectedPaths.length} selected item(s) from server files?`,
                        )
                      ) {
                        bulkDeleteServerFilesMutation.mutate(serverSelectedPaths);
                      }
                    }}
                  >
                    <Trash2 size={16} />
                    {serverSelectedPaths.length > 1
                      ? `Delete (${serverSelectedPaths.length})`
                      : "Delete"}
                  </button>
                  <button
                    className="icon-button command-refresh"
                    onClick={() =>
                      void queryClient.invalidateQueries({ queryKey: ["server-files"] })
                    }
                    title="Refresh server files"
                  >
                    <RefreshCw size={16} />
                  </button>
                </div>
                <div className="server-address">
                  {serverBreadcrumbs(serverPath).map((crumb, index) => (
                    <span className="crumb-group" key={crumb.path || "server-root"}>
                      {index === 0 ? <Server size={15} /> : <ChevronRight size={14} />}
                      <button
                        className="crumb"
                        onClick={() => navigateServerTo(crumb.path)}
                      >
                        {crumb.name}
                      </button>
                    </span>
                  ))}
                </div>
                <dl className="system-list server-meta">
                  <div>
                    <dt>Mode</dt>
                    <dd>{serverStatus?.mode ?? "local"}</dd>
                  </div>
                  <div>
                    <dt>Root</dt>
                    <dd>{serverStatus?.root ?? "Checking..."}</dd>
                  </div>
                </dl>
                <div
                  className="server-file-list"
                  aria-busy={serverFilesQuery.isLoading}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleServerDrop}
                >
                  <div className="server-file-head">
                    <span>
                      <label className="table-select-name">
                        <input
                          type="checkbox"
                          checked={allServerItemsSelected}
                          onChange={() => {
                            if (allServerItemsSelected) {
                              setServerSelectedPaths([]);
                              setServerSelectedPath(null);
                            } else {
                              setServerSelectedPaths(serverItems.map((item) => item.path));
                              setServerSelectedPath(serverItems[0]?.path ?? null);
                            }
                          }}
                        />
                        Name
                      </label>
                    </span>
                    <span>Size</span>
                    <span>Modified</span>
                  </div>
                  <div className="server-file-scroll">
                    {serverItems.map((item) => (
                      <div
                        className={`server-file-row ${
                          serverSelectedPaths.includes(item.path) ? "selected" : ""
                        } ${serverDropTargetPath === item.path ? "drop-target" : ""}`}
                        key={item.path}
                        role="button"
                        tabIndex={0}
                        draggable={serverRenamingPath !== item.path}
                        onClick={() => selectOnlyServerItem(item)}
                        onDoubleClick={() =>
                          item.kind === "folder"
                            ? openServerFolder(item)
                            : downloadServerItem(item)
                        }
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            if (item.kind === "folder") openServerFolder(item);
                            else downloadServerItem(item);
                          }
                        }}
                        onDragStart={(event) => startServerDrag(event, item)}
                        onDragEnd={() => {
                          setServerDraggedPath(null);
                          setServerDropTargetPath(null);
                        }}
                        onDragOver={(event) => markServerDropTarget(event, item)}
                        onDragLeave={() => {
                          if (serverDropTargetPath === item.path) setServerDropTargetPath(null);
                        }}
                        onDrop={(event) => moveServerItemToFolder(event, item)}
                      >
                        <span className="file-name">
                          <input
                            className="row-checkbox"
                            type="checkbox"
                            checked={serverSelectedPaths.includes(item.path)}
                            aria-label={`Select ${item.name}`}
                            onChange={() => toggleServerItemSelection(item)}
                            onClick={(event) => event.stopPropagation()}
                            onDoubleClick={(event) => event.stopPropagation()}
                          />
                          <span className="file-icon">
                            {item.kind === "folder" ? <Folder size={18} /> : <FileIcon size={18} />}
                          </span>
                          {serverRenamingPath === item.path ? (
                            <form className="rename-form" onSubmit={submitServerRename}>
                              <input
                                autoFocus
                                value={serverRenameValue}
                                onBlur={(event) => event.currentTarget.form?.requestSubmit()}
                                onChange={(event) => setServerRenameValue(event.target.value)}
                                onClick={(event) => event.stopPropagation()}
                                onDoubleClick={(event) => event.stopPropagation()}
                              />
                            </form>
                          ) : (
                            item.name
                          )}
                        </span>
                        <span>{item.kind === "folder" ? "-" : formatBytes(item.size)}</span>
                        <span>{serverFileDate(item.modifiedAt)}</span>
                      </div>
                    ))}
                    {!serverItems.length && (
                      <div className="empty-state compact">
                        <Server size={24} />
                        <strong>{serverFilesQuery.isLoading ? "Loading server files" : "Folder is empty"}</strong>
                        <span>Drop files here or create a folder in Server Files.</span>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
            {sidePanel === "trash" && (
              <>
                <div className="system-heading">
                  <Trash2 size={22} />
                  <div>
                    <h2>Trash Bin</h2>
                    <p>
                      Restore deleted items or remove them permanently. Permanent delete also
                      removes synced files from your Telegram storage channel.
                    </p>
                  </div>
                </div>
                <div className="trash-actions">
                  <button className="button system-back" onClick={openRoot}>
                    <ArrowLeft size={16} />
                    Back to files
                  </button>
                  <label className="selection-control">
                    <input
                      type="checkbox"
                      checked={
                        Boolean(trashItems.length) &&
                        trashSelectedIds.length === trashItems.length
                      }
                      onChange={() => {
                        if (trashSelectedIds.length === trashItems.length) {
                          setTrashSelectedIds([]);
                        } else {
                          setTrashSelectedIds(trashItems.map((item) => item.id));
                        }
                      }}
                    />
                    Select all
                  </label>
                  <button
                    className="tool-button"
                    disabled={!trashSelectedIds.length || bulkRestoreMutation.isPending}
                    onClick={() => bulkRestoreMutation.mutate(trashSelectedIds)}
                  >
                    <RotateCcw size={16} />
                    {trashSelectedIds.length > 1
                      ? `Restore (${trashSelectedIds.length})`
                      : "Restore"}
                  </button>
                  <button
                    className="tool-button"
                    disabled={!trashSelectedFiles.length || isBulkDownloading}
                    onClick={() => void downloadSelectedFiles(trashSelectedFiles)}
                  >
                    <Download size={16} />
                    {isBulkDownloading
                      ? "Downloading..."
                      : trashSelectedFiles.length > 1
                        ? `Download (${trashSelectedFiles.length})`
                        : "Download"}
                  </button>
                  <button
                    className="tool-button danger"
                    disabled={!trashSelectedIds.length || isTrashDeleting}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete ${trashSelectedIds.length} selected item(s) permanently?`,
                        )
                      ) {
                        bulkPermanentDeleteMutation.mutate(trashSelectedIds);
                      }
                    }}
                  >
                    <Trash2 size={16} className={bulkPermanentDeleteMutation.isPending ? "spinning" : ""} />
                    {bulkPermanentDeleteMutation.isPending ? "Deleting..." : "Delete permanently"}
                  </button>
                  <button
                    className="tool-button danger trash-empty"
                    disabled={!trashItems.length || emptyTrashMutation.isPending}
                    onClick={() => {
                      if (window.confirm("Permanently delete every item in Trash Bin?")) {
                        emptyTrashMutation.mutate();
                      }
                    }}
                  >
                    <Trash2 size={16} className={emptyTrashMutation.isPending ? "spinning" : ""} />
                    {emptyTrashMutation.isPending ? "Emptying..." : "Empty trash"}
                  </button>
                </div>
                {renderDeleteFeedback()}
                <DeletionJobBanners
                  failedJobs={failedDeletionJobs}
                  processingJobs={processingDeletionJobs}
                  queuedJobs={queuedDeletionJobs}
                  onRetry={() => retryDeletionJobsMutation.mutate()}
                  isRetrying={retryDeletionJobsMutation.isPending}
                />
                {trashItems.length ? (
                  <div
                    className="trash-list"
                    aria-busy={trashQuery.isLoading || emptyTrashMutation.isPending}
                  >
                    {trashItems.map((item) => (
                      <div
                        className={`trash-row ${trashSelectedIds.includes(item.id) ? "selected" : ""}`}
                        key={item.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => {
                          setTrashSelectedIds([item.id]);
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={trashSelectedIds.includes(item.id)}
                          aria-label={`Select ${item.name}`}
                          onChange={() => toggleTrashSelection(item)}
                          onClick={(event) => event.stopPropagation()}
                        />
                        {item.kind === "folder" ? <Folder size={18} /> : <FileIcon size={18} />}
                        <span>
                          <strong>{item.name}</strong>
                          <small>{item.kind === "folder" ? "Folder" : formatBytes(item.size)}</small>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state compact">
                    <Trash2 size={24} />
                    <strong>Trash Bin is empty</strong>
                    <span>Deleted files and folders will appear here.</span>
                  </div>
                )}
              </>
            )}
            {sidePanel === "access" && (
              <>
                <div className="system-heading">
                  <Shield size={22} />
                  <div>
                    <h2>Access</h2>
                    <p>Current local account and Telegram session readiness.</p>
                  </div>
                </div>
                <button className="button system-back" onClick={openRoot}>
                  <ArrowLeft size={16} />
                  Back to files
                </button>
                <dl className="system-list">
                  <div>
                    <dt>Email</dt>
                    <dd>{meQuery.data?.email ?? "Signed in"}</dd>
                  </div>
                  <div>
                    <dt>Telegram session</dt>
                    <dd>
                      {meQuery.data?.hasTelegramSession
                        ? "Saved for this account"
                        : status?.ready
                          ? "Configured in .env"
                          : "Not configured"}
                    </dd>
                  </div>
                  <div>
                    <dt>API credentials</dt>
                    <dd>
                      {meQuery.data?.hasTelegramApiCredentials
                        ? "Available"
                        : "Not configured"}
                    </dd>
                  </div>
                  <div>
                    <dt>Storage</dt>
                    <dd>{status?.ready ? "Ready" : "Waiting for session"}</dd>
                  </div>
                </dl>
              </>
            )}
            {sidePanel === "account" && (
              <>
                <div className="system-heading">
                  <UserRound size={22} />
                  <div>
                    <h2>Account settings</h2>
                    <p>Change the email or password used to sign in to TeleDrive.</p>
                  </div>
                </div>
                <button className="button system-back" type="button" onClick={openRoot}>
                  <ArrowLeft size={16} />
                  Back to files
                </button>
                <form
                  className="account-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setAccountMessage("");
                    if (newPassword && newPassword !== confirmPassword) {
                      setAccountMessage("New password and confirmation do not match.");
                      return;
                    }
                    accountMutation.mutate();
                  }}
                >
                  <label>
                    Email
                    <input
                      type="email"
                      value={accountEmail}
                      onChange={(event) => setAccountEmail(event.target.value)}
                      autoComplete="email"
                    />
                  </label>
                  <label>
                    Current password
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(event) => setCurrentPassword(event.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </label>
                  <label>
                    New password <span>Optional</span>
                    <input
                      type="password"
                      minLength={8}
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      autoComplete="new-password"
                    />
                  </label>
                  <label>
                    Confirm new password
                    <input
                      type="password"
                      minLength={8}
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      autoComplete="new-password"
                      disabled={!newPassword}
                    />
                  </label>
                  {accountMessage && <p className="account-message">{accountMessage}</p>}
                  <button
                    className="tool-button primary"
                    type="submit"
                    disabled={!currentPassword || accountMutation.isPending}
                  >
                    {accountMutation.isPending ? "Saving..." : "Save account settings"}
                  </button>
                </form>
                {meQuery.data?.isOperator && (
                  <section className="account-form">
                    <h3>Registration</h3>
                    <p>
                      {registrationSettingsQuery.data
                        ? "New users can create an account."
                        : "New user registration is disabled."}
                    </p>
                    <label className="selection-control">
                      <input
                        type="checkbox"
                        checked={registrationSettingsQuery.data ?? false}
                        disabled={
                          registrationSettingsQuery.isLoading ||
                          registrationSettingsMutation.isPending
                        }
                        onChange={(event) =>
                          registrationSettingsMutation.mutate(event.target.checked)
                        }
                      />
                      Allow new user registration
                    </label>
                    {registrationSettingsMutation.error && (
                      <p className="account-message">Could not update registration settings.</p>
                    )}
                  </section>
                )}
                <section className="account-form">
                  <h3>Storage recovery</h3>
                  <p>
                    Save an encrypted drive manifest to your private Telegram channel, then restore it after a database loss.
                    Keep the original ENCRYPTION_KEY: without it, existing manifests cannot be read.
                    Only the latest manifest is kept; older copies are removed automatically.
                  </p>
                  <div className="stacked-actions">
                    <button className="tool-button" type="button" disabled={createManifestMutation.isPending} onClick={() => createManifestMutation.mutate()}>
                      {createManifestMutation.isPending ? "Saving manifest…" : "Save recovery manifest"}
                    </button>
                    <button className="tool-button" type="button" disabled={restoreManifestMutation.isPending} onClick={() => restoreManifestMutation.mutate()}>
                      {restoreManifestMutation.isPending ? "Restoring…" : "Restore latest manifest"}
                    </button>
                    <button className="tool-button" type="button" disabled={cleanupManifestsMutation.isPending} onClick={() => cleanupManifestsMutation.mutate()}>
                      {cleanupManifestsMutation.isPending ? "Cleaning…" : "Clean up old manifests"}
                    </button>
                    <button
                      className="tool-button danger"
                      type="button"
                      disabled={purgeChannelMutation.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Delete every file in your Telegram storage channel? The latest recovery manifest is kept if available.",
                          )
                        ) {
                          purgeChannelMutation.mutate();
                        }
                      }}
                    >
                      {purgeChannelMutation.isPending ? "Cleaning channel…" : "Clean up Telegram channel"}
                    </button>
                    <button className="tool-button" type="button" disabled={importTelegramRecoveryMutation.isPending} onClick={() => importTelegramRecoveryMutation.mutate()}>
                      Import Telegram files without manifest
                    </button>
                  </div>
                  {recoveryMessage && <p className="account-message">{recoveryMessage}</p>}
                </section>
                {deletionJobsQuery.data?.length ? (
                  <section className="account-form">
                    <h3>Telegram cleanup</h3>
                    <p>
                      Files removed from TeleDrive are deleted from your Telegram storage channel in
                      one batch connection. Failed cleanups stay listed until retried successfully.
                    </p>
                    <button
                      className="tool-button"
                      type="button"
                      disabled={retryDeletionJobsMutation.isPending || !deletionJobsQuery.data.length}
                      onClick={() => retryDeletionJobsMutation.mutate()}
                    >
                      {retryDeletionJobsMutation.isPending ? "Retrying…" : "Retry Telegram cleanup"}
                    </button>
                    <ul className="deletion-job-list">
                      {deletionJobsQuery.data.map((job) => (
                        <li key={job.id}>
                          <strong>{job.status}</strong> · attempt {job.attempts}
                          {job.lastError ? ` · ${job.lastError}` : ""}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </>
            )}
            {sidePanel === "setup" && (
              <>
                <div className="system-heading">
                  <KeyRound size={22} />
                  <div>
                    <h2>Telegram setup</h2>
                    <p>Connect your own Telegram account as private file storage.</p>
                  </div>
                </div>
                <button className="button system-back" onClick={openRoot}>
                  <ArrowLeft size={16} />
                  Back to files
                </button>

                <div className="setup-grid">
                  <section className="setup-section">
                    <div className="setup-step">1</div>
                    <div className="setup-copy">
                      <h3>Get API ID and API Hash</h3>
                      <p>
                        Open Telegram's developer page, sign in with your Telegram number,
                        then create an app. Use any simple app title like TeleDrive.
                      </p>
                      <a
                        className="setup-link"
                        href="https://my.telegram.org/apps"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open my.telegram.org
                        <ExternalLink size={15} />
                      </a>
                    </div>
                  </section>

                  <section className="setup-section">
                    <div className="setup-step">2</div>
                    <form
                      className="setup-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        telegramCredentialsMutation.mutate();
                      }}
                    >
                      <div className="setup-copy">
                        <h3>Save API credentials</h3>
                        <p>
                          These values identify your Telegram app. They are stored encrypted
                          for this TeleDrive account.
                        </p>
                      </div>
                      <label>
                        Telegram API ID
                        <input
                          inputMode="numeric"
                          value={telegramApiId}
                          onChange={(event) => setTelegramApiId(event.target.value)}
                          placeholder="Example: 12345678"
                        />
                      </label>
                      <label>
                        Telegram API Hash
                        <input
                          value={telegramApiHash}
                          onChange={(event) => setTelegramApiHash(event.target.value)}
                          placeholder="32 character hash from Telegram"
                        />
                      </label>
                      <button
                        className="tool-button primary"
                        type="submit"
                        disabled={!telegramApiId || !telegramApiHash}
                      >
                        <KeyRound size={15} />
                        Save API credentials
                      </button>
                    </form>
                  </section>

                  <section className="setup-section">
                    <div className="setup-step">3</div>
                    <form
                      className="setup-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (telegramLoginStep === "phone") {
                          telegramLoginStartMutation.mutate();
                        } else {
                          telegramLoginVerifyMutation.mutate();
                        }
                      }}
                    >
                      <div className="setup-copy">
                        <h3>Login to Telegram</h3>
                        <p>
                          Use the same phone number as your Telegram account. Telegram
                          sends the OTP to your Telegram app, not as a normal SMS in many cases.
                        </p>
                      </div>
                      <label>
                        Phone number
                        <input
                          value={telegramPhone}
                          onChange={(event) => setTelegramPhone(event.target.value)}
                          placeholder="Example: +628123456789"
                        />
                      </label>
                      {telegramLoginStep !== "phone" && (
                        <label>
                          Telegram OTP
                          <input
                            inputMode="numeric"
                            value={telegramCode}
                            onChange={(event) => setTelegramCode(event.target.value)}
                            placeholder="Code from Telegram"
                          />
                        </label>
                      )}
                      {telegramLoginStep === "password" && (
                        <label>
                          Telegram 2FA password
                          <input
                            type="password"
                            value={telegramPassword}
                            onChange={(event) => setTelegramPassword(event.target.value)}
                            placeholder="Telegram cloud password"
                          />
                        </label>
                      )}
                      {telegramLoginMessage && (
                        <p className="setup-message">{telegramLoginMessage}</p>
                      )}
                      <button
                        className="tool-button primary"
                        type="submit"
                        disabled={
                          telegramLoginStartMutation.isPending ||
                          telegramLoginVerifyMutation.isPending ||
                          (telegramLoginStep === "phone" && !telegramPhone) ||
                          (telegramLoginStep === "code" && !telegramCode) ||
                          (telegramLoginStep === "password" && !telegramPassword)
                        }
                      >
                        <KeyRound size={15} />
                        {telegramLoginStep === "phone"
                          ? "Send OTP"
                          : telegramLoginStep === "password"
                            ? "Verify password"
                            : "Verify OTP"}
                      </button>
                    </form>
                  </section>

                  <section className="setup-section setup-advanced">
                    <div className="setup-step">4</div>
                    <form
                      className="setup-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        telegramSessionMutation.mutate(telegramSession);
                      }}
                    >
                      <div className="setup-copy">
                        <h3>Advanced: paste session manually</h3>
                        <p>
                          Use this only if you already generated a Telethon StringSession.
                          The session is sensitive and should never be committed to a repo.
                        </p>
                      </div>
                      <textarea
                        value={telegramSession}
                        onChange={(event) => setTelegramSession(event.target.value)}
                        placeholder="Paste TELEGRAM_SESSION here"
                        rows={4}
                      />
                      <button
                        className="tool-button"
                        type="submit"
                        disabled={!telegramSession || telegramSessionMutation.isPending}
                      >
                        Save pasted session
                      </button>
                    </form>
                  </section>

                  <section className={status?.ready ? "setup-status ready" : "setup-status"}>
                    <strong>{status?.ready ? "Telegram storage is ready" : "Setup incomplete"}</strong>
                    <span>
                      {status?.ready
                        ? "Uploads can sync to your private Telegram storage channel."
                        : status?.details ??
                          "Save API credentials and a Telegram session to enable syncing."}
                    </span>
                  </section>
                </div>
              </>
            )}
            {sidePanel === "api" && (
              <>
                <div className="system-heading">
                  <Info size={22} />
                  <div>
                    <h2>API status</h2>
                    <p>Live status from the authenticated storage endpoint.</p>
                  </div>
                </div>
                <button className="button system-back" onClick={openRoot}>
                  <ArrowLeft size={16} />
                  Back to files
                </button>
                <dl className="system-list">
                  <div>
                    <dt>TeleDrive version</dt>
                    <dd>{updateStatus?.currentVersion ?? "Checking..."}</dd>
                  </div>
                  <div>
                    <dt>Latest release</dt>
                    <dd>
                      {updateStatus?.latestVersion ??
                        (updateStatus?.checked ? "No release found" : "Not checked")}
                    </dd>
                  </div>
                  <div>
                    <dt>Update</dt>
                    <dd>
                      {updateStatus?.updateAvailable
                        ? "Available"
                        : updateStatus?.checked
                          ? "Up to date"
                          : updateStatus?.details ?? "Checking..."}
                    </dd>
                  </div>
                  <div>
                    <dt>Provider</dt>
                    <dd>{status?.provider ?? "telegram-private-channel"}</dd>
                  </div>
                  <div>
                    <dt>Channel</dt>
                    <dd>{status?.channelName ?? "TeleDrive Storage"}</dd>
                  </div>
                  <div>
                    <dt>Connection</dt>
                    <dd>{status?.connected ? "Connected" : "Not connected"}</dd>
                  </div>
                  <div>
                    <dt>Details</dt>
                    <dd>{status?.details ?? "Checking..."}</dd>
                  </div>
                </dl>
                {updateStatus?.updateAvailable && (
                  <a
                    className="button wide update-link"
                    href={updateStatus.releaseUrl ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => {
                      if (!updateStatus.releaseUrl) event.preventDefault();
                    }}
                  >
                    <RefreshCw size={17} />
                    View {updateStatus.releaseName ?? updateStatus.latestVersion}
                    <ExternalLink size={16} />
                  </a>
                )}
                <button
                  className="button wide"
                  type="button"
                  onClick={() => void refreshStatus()}
                  disabled={isRefreshingStatus}
                >
                  {isRefreshingStatus ? "Refreshing..." : "Refresh status"}
                  <RefreshCw className={isRefreshingStatus ? "spinning" : ""} size={17} />
                </button>
                {statusRefreshedAt && (
                  <p className="refresh-feedback">
                    Updated at {statusRefreshedAt.toLocaleTimeString()}
                  </p>
                )}
              </>
            )}
          </section>
        ) : (
        <div className={`content-grid ${showDetails ? "" : "details-hidden"} ${viewMode === "compact" ? "compact-view" : ""}`}>
          <section
            className={`file-panel ${isDragging ? "dragging" : ""} ${isDriveDeleting ? "deleting" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            {table.getHeaderGroups().map((headerGroup) => (
              <div className="table-head" key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <span key={header.id}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </span>
                ))}
              </div>
            ))}

            <div className="file-list" aria-busy={filesQuery.isLoading || isDriveDeleting}>
              {table.getRowModel().rows.map((row) => (
                <div
                  key={row.id}
                  className={`file-row ${selectedIds.includes(row.original.id) ? "selected" : ""} ${dropTargetId === row.original.id ? "drop-target" : ""}`}
                  role="button"
                  tabIndex={0}
                  draggable={renamingId !== row.original.id}
                  onClick={(event) => handleDriveItemClick(row.original, event)}
                  onDoubleClick={() => openFolder(row.original)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && renamingId !== row.original.id) {
                      openFolder(row.original);
                    }
                  }}
                  onDragStart={(event) => startItemDrag(event, row.original)}
                  onDragEnd={() => {
                    setDraggedItemId(null);
                    setDropTargetId(null);
                  }}
                  onDragOver={(event) => {
                    if (row.original.kind === "folder") {
                      markFolderDropTarget(event, row.original);
                    }
                  }}
                  onDragLeave={() => {
                    if (dropTargetId === row.original.id) setDropTargetId(null);
                  }}
                  onDrop={(event) => {
                    if (row.original.kind === "folder") {
                      moveItemToFolder(event, row.original);
                    }
                  }}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    selectOnly(row.original);
                    setContextMenu({
                      x: event.clientX,
                      y: event.clientY,
                      item: row.original,
                    });
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <span key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </span>
                  ))}
                </div>
              ))}
              {!filteredItems.length && (
                <div className="empty-state">
                  <FilePlus2 size={24} />
                  <strong>{query ? "No files found" : "This folder is empty"}</strong>
                  <span>Drop files here or create a folder in {currentFolder.name}.</span>
                </div>
              )}
            </div>
            {isDragging && <div className="drop-overlay">Drop to add files here</div>}
          </section>

          <aside className="detail-panel">
            {selectedItem ? (
              <>
                <div className="detail-heading">
                  <div className="detail-icon">
                    {selectedItem.kind === "folder" ? <Folder size={24} /> : <FileIcon size={24} />}
                  </div>
                  <div>
                    <p>Properties</p>
                    <h2>{selectedItem.name}</h2>
                  </div>
                </div>
                <dl>
                  <div>
                    <dt>Type</dt>
                    <dd>{formatFileType(selectedItem)}</dd>
                  </div>
                  <div>
                    <dt>Size</dt>
                    <dd>{formatBytes(selectedItem.size)}</dd>
                  </div>
                  <div>
                    <dt>Location</dt>
                    <dd>{currentFolder.name}</dd>
                  </div>
                  <div>
                    <dt>Provider</dt>
                    <dd>Telegram private channel</dd>
                  </div>
                  <div>
                    <dt>Sync</dt>
                    <dd>
                      {selectedItem.syncStatus}
                      {selectedItem.syncError ? `: ${selectedItem.syncError}` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Remote id</dt>
                    <dd>{selectedItem.storage.remoteId ?? "Metadata only"}</dd>
                  </div>
                </dl>
                {selectedItem.kind === "file" ? (
                  <div className="stacked-actions">
                    <button className="button wide" disabled={!isEditableTextFile(selectedItem)} onClick={() => void openTextEditor({
                      source: "drive",
                      id: selectedItem.id,
                      name: selectedItem.name,
                      size: selectedItem.size,
                      mimeType: selectedItem.mimeType,
                    })}>
                      Edit text
                      <Edit3 size={17} />
                    </button>
                    <button className="button wide" onClick={() => openDownload(selectedItem)}>
                      Download file
                      <Download size={17} />
                    </button>
                  </div>
                ) : (
                  <button className="button wide" onClick={() => openFolder(selectedItem)}>
                    Open folder
                    <ChevronRight size={17} />
                  </button>
                )}
              </>
            ) : (
              <div className="empty-state compact">
                <FilePlus2 size={24} />
                <strong>Select an item</strong>
              </div>
            )}
          </aside>
        </div>
        )}
      </section>

      {contextMenu && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.item.kind === "folder" && (
            <button onClick={() => openFolder(contextMenu.item)}>
              <FolderOpen size={15} />
              Open
            </button>
          )}
          {contextMenu.item.kind === "file" && (
            <button onClick={() => openDownload(contextMenu.item)}>
              <Download size={15} />
              Download
            </button>
          )}
          {contextMenu.item.kind === "file" && (
            <button disabled={!isEditableTextFile(contextMenu.item)} onClick={() => void openTextEditor({
              source: "drive",
              id: contextMenu.item.id,
              name: contextMenu.item.name,
              size: contextMenu.item.size,
              mimeType: contextMenu.item.mimeType,
            })}>
              <Edit3 size={15} />
              Edit text
            </button>
          )}
          {contextMenu.item.kind === "file" && (
            <button onClick={() => syncMutation.mutate(contextMenu.item.id)}>
              <CloudUpload size={15} />
              Sync to Telegram
            </button>
          )}
          <button onClick={() => startRename(contextMenu.item)}>
            <Edit3 size={15} />
            Rename
          </button>
          <button
            className="danger"
            disabled={isDriveDeleting}
            onClick={() => deleteFileMutation.mutate(contextMenu.item.id)}
          >
            <Trash2 size={15} className={deleteFileMutation.isPending ? "spinning" : ""} />
            {deleteFileMutation.isPending ? "Deleting..." : "Delete"}
          </button>
        </div>
      )}
      {editorTarget && (
        <TextEditorDialog
          document={editorDocument}
          fileName={editorTarget.name}
          loading={editorLoading}
          saving={saveEditorMutation.isPending}
          error={editorError}
          onClose={() => {
            editorRequestRef.current += 1;
            setEditorDocument(null);
            setEditorTarget(null);
            setEditorError("");
            setEditorConflict(false);
            setEditorLoading(false);
          }}
          onReload={editorConflict ? () => void openTextEditor(editorTarget) : undefined}
          onSave={(payload) => saveEditorMutation.mutate({
            target: editorTarget,
            payload,
            revision: editorDocument?.revision,
          })}
        />
      )}
      <DevHealthBadge />
    </main>
  );
}
