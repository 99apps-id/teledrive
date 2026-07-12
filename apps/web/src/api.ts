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
    if (error?.response?.status === 401) {
      csrfToken = "";
      window.dispatchEvent(new Event("teledrive:auth-expired"));
    }
    const detail = error?.response?.data?.detail;
    if (typeof detail === "string" && detail) {
      return Promise.reject(new Error(detail));
    }
    return Promise.reject(error);
  },
);

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

export function logout() {
  return api.post<void>("/auth/logout").finally(() => {
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

export function uploadFile(file: File, parentId: string | null) {
  const formData = new FormData();
  formData.append("file", file);
  if (parentId) formData.append("parent_id", parentId);

  return api
    .post<{ data: PythonDriveItem }>("/files/upload", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
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
  return api.delete<void>(`/trash/${id}`).then(() => undefined);
}

export function emptyTrash() {
  return api.delete<void>("/trash").then(() => undefined);
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

export function getUpdateStatus() {
  return api
    .get<{ data: PythonUpdateStatus }>("/update/status")
    .then((response) => mapUpdateStatus(response.data.data));
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

export function uploadServerFile(path: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return api
    .post<{ data: PythonServerFileItem }>("/server-files/upload", formData, {
      params: { path },
      headers: {
        "Content-Type": "multipart/form-data",
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
