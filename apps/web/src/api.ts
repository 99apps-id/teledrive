import axios from "axios";
import type {
  CreateFileRequest,
  DriveItem,
  StorageStatus,
  UpdateDriveItemRequest,
} from "@teledrive/shared";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
function readCsrfCookie() {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("teledrive_csrf="))
    ?.split("=")[1] ?? "";
}

let csrfToken = readCsrfCookie();
let sessionActive = false;

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  if (csrfToken && !["get", "head", "options"].includes(config.method?.toLowerCase() ?? "")) {
    config.headers["X-CSRF-Token"] = csrfToken;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && sessionActive) {
      sessionActive = false;
      csrfToken = "";
      window.dispatchEvent(new Event("teledrive:auth-expired"));
    }
    const detail = error?.response?.data?.detail;
    const status = error?.response?.status;
    if (typeof detail === "string" && detail) {
      return Promise.reject(Object.assign(new Error(detail), { status }));
    }
    if (typeof status === "number") {
      return Promise.reject(Object.assign(error instanceof Error ? error : new Error("Request failed"), { status }));
    }
    return Promise.reject(error);
  },
);

export function formatApiError(error: unknown, fallback: string): string {
  const status = (error as { status?: number })?.status;
  if (status === 404) {
    return "API endpoint not found. Run npm run dev:clean && npm run dev, then retry.";
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function formatAuthError(error: unknown): string {
  const status = (error as { status?: number })?.status;
  if (error instanceof Error && !status && error.message.toLowerCase().includes("network")) {
    return "Cannot reach the API. Run npm run dev, then try again.";
  }
  if (status === 401) {
    return "Invalid email or password.";
  }
  if (status === 403) {
    return "Registration is disabled. Sign in with an existing account or ask the operator to enable registration.";
  }
  if (status === 409) {
    return "This email is already registered. Sign in instead.";
  }
  if (status === 429) {
    return "Too many attempts. Wait a minute, then try again.";
  }
  return formatApiError(error, "Authentication failed.");
}

export interface AuthUser {
  id: string;
  email: string;
  isOperator: boolean;
  hasTelegramApiCredentials: boolean;
  hasTelegramSession: boolean;
}

export interface TelegramLoginResult {
  nextStep: "code" | "password" | "done";
  message: string;
  user: AuthUser | null;
}

export interface ServerFileItem {
  name: string;
  path: string;
  kind: "file" | "folder";
  size: number;
  modifiedAt: string | null;
}

export interface TextFileContent {
  name: string;
  content: string;
  encoding: "utf-8" | "utf-8-bom" | "utf-16le" | "utf-16be" | "windows-1252";
  newline: "lf" | "crlf";
  revision?: string;
}

export interface SaveTextFilePayload {
  content: string;
  encoding: TextFileContent["encoding"];
  newline: TextFileContent["newline"];
  revision?: string;
}

export interface DeletionJob {
  id: string;
  status: string;
  attempts: number;
  nextAttemptAt: string;
  lastError: string | null;
  createdAt: string;
}

export interface ServerFilesStatus {
  mode: string;
  root: string;
  ready: boolean;
  details: string;
}

export interface ServerFilesConfig {
  mode: "local" | "sftp";
  localRoot: string;
  sftpHost: string;
  sftpPort: number;
  sftpUser: string;
  hasSftpPassword: boolean;
  sftpKeyPath: string;
  sftpRoot: string;
  source: string;
}

export interface ServerFilesConfigPayload {
  mode: "local" | "sftp";
  localRoot: string;
  sftpHost: string;
  sftpPort: number;
  sftpUser: string;
  sftpPassword: string;
  sftpKeyPath: string;
  sftpRoot: string;
}

export interface UpdateStatus {
  currentVersion: string;
  latestVersion: string | null;
  updateAvailable: boolean;
  releaseUrl: string | null;
  releaseName: string | null;
  publishedAt: string | null;
  checked: boolean;
  details: string;
}

export interface WebDavStatus {
  enabled: boolean;
  mountPath: string;
  auth: string;
  cachePath: string;
  cacheMaxBytes: number;
  details: string;
  rcloneExample: string;
}

interface PythonAuthUser {
  id: string;
  email: string;
  is_operator: boolean;
  has_telegram_api_credentials: boolean;
  has_telegram_session: boolean;
}

interface PythonTelegramLoginResult {
  next_step: "code" | "password" | "done";
  message: string;
  user: PythonAuthUser | null;
}

function mapUser(user: PythonAuthUser): AuthUser {
  return {
    id: user.id,
    email: user.email,
    isOperator: user.is_operator,
    hasTelegramApiCredentials: user.has_telegram_api_credentials,
    hasTelegramSession: user.has_telegram_session,
  };
}

function mapTelegramLoginResult(result: PythonTelegramLoginResult): TelegramLoginResult {
  return {
    nextStep: result.next_step,
    message: result.message,
    user: result.user ? mapUser(result.user) : null,
  };
}

interface PythonDriveItem {
  id: string;
  kind: "file" | "folder";
  name: string;
  parent_id: string | null;
  size: number;
  mime_type: string | null;
  created_at: string;
  updated_at: string;
  storage: {
    provider: "telegram-private-channel";
    remote_id: string | null;
    channel_name: string;
  };
  sync_status: string;
  sync_error: string | null;
}

interface PythonStorageStatus {
  provider: "telegram-private-channel";
  channel_name: string;
  connected: boolean;
  ready: boolean;
  details: string;
}

interface PythonServerFileItem {
  name: string;
  path: string;
  kind: "file" | "folder";
  size: number;
  modified_at: string | null;
}

interface PythonServerFilesStatus {
  mode: string;
  root: string;
  ready: boolean;
  details: string;
}

interface PythonServerFilesConfig {
  mode: "local" | "sftp";
  local_root: string;
  sftp_host: string;
  sftp_port: number;
  sftp_user: string;
  has_sftp_password: boolean;
  sftp_key_path: string;
  sftp_root: string;
  source: string;
}

interface PythonUpdateStatus {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_url: string | null;
  release_name: string | null;
  published_at: string | null;
  checked: boolean;
  details: string;
}

interface PythonWebDavStatus {
  enabled: boolean;
  mount_path: string;
  auth: string;
  cache_path: string;
  cache_max_bytes: number;
  details: string;
  rclone_example: string;
}

function mapDriveItem(item: PythonDriveItem): DriveItem {
  return {
    id: item.id,
    kind: item.kind,
    name: item.name,
    parentId: item.parent_id,
    size: item.size,
    mimeType: item.mime_type,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    storage: {
      provider: item.storage.provider,
      remoteId: item.storage.remote_id,
      channelName: item.storage.channel_name,
    },
    syncStatus: item.sync_status,
    syncError: item.sync_error,
  };
}

function mapStorageStatus(status: PythonStorageStatus): StorageStatus {
  return {
    provider: status.provider,
    channelName: status.channel_name,
    connected: status.connected,
    ready: status.ready,
    details: status.details,
  };
}

function mapServerFileItem(item: PythonServerFileItem): ServerFileItem {
  return {
    name: item.name,
    path: item.path,
    kind: item.kind,
    size: item.size,
    modifiedAt: item.modified_at,
  };
}

function mapServerFilesStatus(status: PythonServerFilesStatus): ServerFilesStatus {
  return {
    mode: status.mode,
    root: status.root,
    ready: status.ready,
    details: status.details,
  };
}

function mapServerFilesConfig(config: PythonServerFilesConfig): ServerFilesConfig {
  return {
    mode: config.mode,
    localRoot: config.local_root,
    sftpHost: config.sftp_host,
    sftpPort: config.sftp_port,
    sftpUser: config.sftp_user,
    hasSftpPassword: config.has_sftp_password,
    sftpKeyPath: config.sftp_key_path,
    sftpRoot: config.sftp_root,
    source: config.source,
  };
}

function mapUpdateStatus(status: PythonUpdateStatus): UpdateStatus {
  return {
    currentVersion: status.current_version,
    latestVersion: status.latest_version,
    updateAvailable: status.update_available,
    releaseUrl: status.release_url,
    releaseName: status.release_name,
    publishedAt: status.published_at,
    checked: status.checked,
    details: status.details,
  };
}

function mapWebDavStatus(status: PythonWebDavStatus): WebDavStatus {
  return {
    enabled: status.enabled,
    mountPath: status.mount_path,
    auth: status.auth,
    cachePath: status.cache_path,
    cacheMaxBytes: status.cache_max_bytes,
    details: status.details,
    rcloneExample: status.rclone_example,
  };
}

function serverFilesPayload(payload: ServerFilesConfigPayload) {
  return {
    mode: payload.mode,
    local_root: payload.localRoot,
    sftp_host: payload.sftpHost,
    sftp_port: payload.sftpPort,
    sftp_user: payload.sftpUser,
    sftp_password: payload.sftpPassword,
    sftp_key_path: payload.sftpKeyPath,
    sftp_root: payload.sftpRoot,
  };
}

export function listFiles(parentId: string | null = null) {
  const query = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : "";
  return api
    .get<{ data: PythonDriveItem[] }>(`/files${query}`)
    .then((response) => response.data.data.map(mapDriveItem));
}

export function register(email: string, password: string) {
  return api
    .post<{ access_token: string; csrf_token: string; user: PythonAuthUser }>("/auth/register", {
      email,
      password,
    })
    .then((response) => ({
      token: response.data.access_token,
      csrfToken: response.data.csrf_token,
      user: mapUser(response.data.user),
    }));
}

export function login(email: string, password: string) {
  return api
    .post<{ access_token: string; csrf_token: string; user: PythonAuthUser }>("/auth/login", {
      email,
      password,
    })
    .then((response) => ({
      token: response.data.access_token,
      csrfToken: response.data.csrf_token,
      user: mapUser(response.data.user),
    }));
}

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function setSessionActive(active: boolean) {
  sessionActive = active;
}

export async function bootstrapSession(): Promise<boolean> {
  csrfToken = readCsrfCookie();
  try {
    await api.get<PythonAuthUser>("/auth/me");
    sessionActive = true;
    return true;
  } catch {
    sessionActive = false;
    csrfToken = readCsrfCookie();
    return false;
  }
}

export function logout() {
  return api.post<void>("/auth/logout").finally(() => {
    sessionActive = false;
    csrfToken = "";
  });
}

export function getMe() {
  return api.get<PythonAuthUser>("/auth/me").then((response) => mapUser(response.data));
}

export function getRegistrationSettings() {
  return api
    .get<{ registration_enabled: boolean }>("/auth/registration-settings")
    .then((response) => response.data.registration_enabled);
}

export function updateRegistrationSettings(registrationEnabled: boolean) {
  return api
    .put<{ registration_enabled: boolean }>("/auth/registration-settings", {
      registration_enabled: registrationEnabled,
    })
    .then((response) => response.data.registration_enabled);
}

export function updateAccount(payload: {
  currentPassword: string;
  email?: string;
  newPassword?: string;
}) {
  return api
    .put<PythonAuthUser>("/auth/account", {
      current_password: payload.currentPassword,
      email: payload.email || undefined,
      new_password: payload.newPassword || undefined,
    })
    .then((response) => mapUser(response.data));
}

export function saveTelegramSession(session: string) {
  return api
    .put<PythonAuthUser>("/auth/telegram-session", { session })
    .then((response) => mapUser(response.data));
}

export function saveTelegramCredentials(apiId: string, apiHash: string) {
  return api
    .put<PythonAuthUser>("/auth/telegram-credentials", {
      api_id: apiId,
      api_hash: apiHash,
    })
    .then((response) => mapUser(response.data));
}

export function startTelegramLogin(phone: string) {
  return api
    .post<PythonTelegramLoginResult>("/auth/telegram-login/start", { phone })
    .then((response) => mapTelegramLoginResult(response.data));
}

export function verifyTelegramLogin(code: string, password?: string) {
  return api
    .post<PythonTelegramLoginResult>("/auth/telegram-login/verify", {
      code: code || undefined,
      password: password || undefined,
    })
    .then((response) => mapTelegramLoginResult(response.data));
}

export function verifyTelegramPassword(password: string) {
  return api
    .post<PythonTelegramLoginResult>("/auth/telegram-login/verify", { password })
    .then((response) => mapTelegramLoginResult(response.data));
}

export function createFolder(name: string, parentId: string | null) {
  return api
    .post<{ data: PythonDriveItem }>("/folders", {
      name,
      parent_id: parentId,
    })
    .then((response) => mapDriveItem(response.data.data));
}

export function createFile(payload: CreateFileRequest) {
  return api
    .post<{ data: PythonDriveItem }>("/files", {
      name: payload.name,
      parent_id: payload.parentId,
      size: payload.size,
      mime_type: payload.mimeType,
    })
    .then((response) => mapDriveItem(response.data.data));
}

export function uploadFile(
  file: File,
  parentId: string | null,
  onProgress?: (percentage: number) => void,
) {
  const formData = new FormData();
  formData.append("file", file);
  if (parentId) formData.append("parent_id", parentId);

  return api
    .post<{ data: PythonDriveItem }>("/files/upload", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (event) => {
        if (event.total) onProgress?.(Math.round((event.loaded / event.total) * 100));
      },
    })
    .then((response) => mapDriveItem(response.data.data));
}

function filenameFromDisposition(disposition: string | undefined) {
  if (!disposition) return null;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
}

export function downloadFile(id: string) {
  return api
    .get<Blob>(`/files/${id}/download`, { responseType: "blob" })
    .then((response) => ({
      blob: response.data,
      filename: filenameFromDisposition(response.headers["content-disposition"]),
    }));
}

export function downloadFilesZip(ids: string[]) {
  return api
    .post<Blob>(
      "/files/download-zip",
      { item_ids: ids },
      { responseType: "blob" },
    )
    .then((response) => ({
      blob: response.data,
      filename: filenameFromDisposition(response.headers["content-disposition"]),
    }));
}

export function copyDriveFileToServer(id: string, serverPath: string) {
  return api
    .post<{ data: PythonServerFileItem }>(`/files/${id}/copy-to-server`, {
      server_path: serverPath,
    })
    .then((response) => mapServerFileItem(response.data.data));
}

export function syncFileToTelegram(id: string) {
  return api
    .post<{ data: PythonDriveItem }>(`/files/${id}/sync`)
    .then((response) => mapDriveItem(response.data.data));
}

export function deleteFile(id: string) {
  return api.delete<void>(`/files/${id}`).then(() => undefined);
}

export function listTrash() {
  return api
    .get<{ data: PythonDriveItem[] }>("/trash")
    .then((response) => response.data.data.map(mapDriveItem));
}

export function restoreFromTrash(id: string) {
  return api
    .post<{ data: PythonDriveItem }>(`/trash/${id}/restore`)
    .then((response) => mapDriveItem(response.data.data));
}

export function deletePermanently(id: string) {
  return api.delete<{ job_ids: string[] }>(`/trash/${id}`).then((response) => response.data);
}

export function deletePermanentlyBulk(ids: string[]) {
  return api
    .post<{ job_ids: string[] }>("/trash/bulk-permanent", { item_ids: ids })
    .then((response) => response.data);
}

export function emptyTrash() {
  return api.delete<{ job_ids: string[] }>("/trash").then((response) => response.data);
}

export function listDeletionJobs(reconcile = false) {
  return api
    .get<{
      data: Array<{
        id: string;
        status: string;
        attempts: number;
        next_attempt_at: string;
        last_error: string | null;
        created_at: string;
      }>;
    }>("/deletion-jobs", {
      params: reconcile ? { reconcile: true } : undefined,
    })
    .then((response) =>
      response.data.data.map((job) => ({
        id: job.id,
        status: job.status,
        attempts: job.attempts,
        nextAttemptAt: job.next_attempt_at,
        lastError: job.last_error,
        createdAt: job.created_at,
      })),
    );
}

export function retryDeletionJobs() {
  return api
    .post<{ data: { attempted: number; failed: number; completed: number } }>("/deletion-jobs/retry")
    .then((response) => response.data.data);
}

export function updateDriveItem(id: string, payload: UpdateDriveItemRequest) {
  return api
    .patch<{ data: PythonDriveItem }>(`/files/${id}`, {
      name: payload.name,
      parent_id: payload.parentId,
    })
    .then((response) => mapDriveItem(response.data.data));
}

export function getStorageStatus() {
  return api
    .get<{ data: PythonStorageStatus }>("/storage/status")
    .then((response) => mapStorageStatus(response.data.data));
}

export function getServerFilesStatus() {
  return api
    .get<{ data: PythonServerFilesStatus }>("/server-files/status")
    .then((response) => mapServerFilesStatus(response.data.data));
}

export function getServerFilesConfig() {
  return api
    .get<{ data: PythonServerFilesConfig }>("/server-files/config")
    .then((response) => mapServerFilesConfig(response.data.data));
}

export interface DevStackStatus {
  api: boolean;
  redis: boolean;
  worker: boolean;
}

export function getDevStackStatus() {
  return api
    .get<{ data: DevStackStatus }>("/dev/stack-status")
    .then((response) => response.data.data)
    .catch(() => ({ api: false, redis: false, worker: false }));
}

export function getUpdateStatus() {
  return api
    .get<{ data: PythonUpdateStatus }>("/update/status")
    .then((response) => mapUpdateStatus(response.data.data));
}

export function getWebDavStatus() {
  return api
    .get<{ data: PythonWebDavStatus }>("/webdav/status")
    .then((response) => mapWebDavStatus(response.data.data));
}

export function saveServerFilesConfig(payload: ServerFilesConfigPayload) {
  return api
    .put<{ data: PythonServerFilesConfig }>(
      "/server-files/config",
      serverFilesPayload(payload),
    )
    .then((response) => mapServerFilesConfig(response.data.data));
}

export function testServerFilesConfig(payload: ServerFilesConfigPayload) {
  return api
    .post<{ data: PythonServerFilesStatus }>(
      "/server-files/config/test",
      serverFilesPayload(payload),
    )
    .then((response) => mapServerFilesStatus(response.data.data));
}

export function listServerFiles(path = "") {
  return api
    .get<{ data: PythonServerFileItem[] }>("/server-files", { params: { path } })
    .then((response) => response.data.data.map(mapServerFileItem));
}

export function createServerFolder(path: string, name: string) {
  return api
    .post<{ data: PythonServerFileItem }>("/server-files/folders", { path, name })
    .then((response) => mapServerFileItem(response.data.data));
}

export function uploadServerFile(
  path: string,
  file: File,
  onProgress?: (percentage: number) => void,
) {
  const formData = new FormData();
  formData.append("file", file);
  return api
    .post<{ data: PythonServerFileItem }>("/server-files/upload", formData, {
      params: { path },
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (event) => {
        if (event.total) onProgress?.(Math.round((event.loaded / event.total) * 100));
      },
    })
    .then((response) => mapServerFileItem(response.data.data));
}

export function downloadServerFile(path: string) {
  return api
    .get<Blob>("/server-files/download", {
      params: { path },
      responseType: "blob",
    })
    .then((response) => ({
      blob: response.data,
      filename: filenameFromDisposition(response.headers["content-disposition"]),
    }));
}

export function updateServerFile(
  path: string,
  payload: { name?: string; parentPath?: string },
) {
  return api
    .patch<{ data: PythonServerFileItem }>("/server-files", {
      path,
      name: payload.name,
      parent_path: payload.parentPath,
    })
    .then((response) => mapServerFileItem(response.data.data));
}

export function deleteServerFile(path: string) {
  return api.delete<void>("/server-files", { params: { path } }).then(() => undefined);
}

export function importServerFileToDrive(path: string, parentId: string | null) {
  return api
    .post<{ data: PythonDriveItem }>("/server-files/import-to-drive", {
      path,
      parent_id: parentId,
    })
    .then((response) => mapDriveItem(response.data.data));
}

export function readDriveTextFile(itemId: string) {
  return api
    .get<{ data: TextFileContent }>(`/files/${itemId}/text`)
    .then((response) => response.data.data);
}

export function saveDriveTextFile(itemId: string, payload: SaveTextFilePayload) {
  return api
    .put<{ data: PythonDriveItem }>(`/files/${itemId}/text`, payload)
    .then((response) => mapDriveItem(response.data.data));
}

export function readServerTextFile(path: string) {
  return api
    .get<{ data: TextFileContent }>("/server-files/text", { params: { path } })
    .then((response) => response.data.data);
}

export function saveServerTextFile(path: string, payload: SaveTextFilePayload) {
  return api
    .put<{ data: TextFileContent }>("/server-files/text", payload, { params: { path } })
    .then((response) => response.data.data);
}

export function createRecoveryManifest() {
  return api.post<{ data: { id: string; created_at: string } }>("/recovery/manifests").then((response) => response.data.data);
}

export function restoreRecoveryManifest() {
  return api.post<{ data: { restored: number } }>("/recovery/manifests/restore").then((response) => response.data.data);
}

export function cleanupStaleManifests() {
  return api
    .post<{ data: { removed: number } }>("/recovery/manifests/cleanup")
    .then((response) => response.data.data);
}

export function purgeChannelStorage() {
  return api
    .post<{ data: { removed: number } }>("/recovery/channel-cleanup")
    .then((response) => response.data.data);
}

export function importTelegramRecovery() {
  return api.post<{ data: { items_processed: number } }>("/recovery/telegram-import").then((response) => response.data.data);
}
