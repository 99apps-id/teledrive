export const TELEDRIVE_STORAGE_CHANNEL = "TeleDrive Storage";

export type FileKind = "file" | "folder";

export type StorageProvider = "telegram-private-channel";

export interface DriveItem {
  id: string;
  kind: FileKind;
  name: string;
  parentId: string | null;
  size: number;
  mimeType: string | null;
  createdAt: string;
  updatedAt: string;
  storage: {
    provider: StorageProvider;
    remoteId: string | null;
    channelName: string;
  };
  syncStatus: string;
  syncError: string | null;
}

export interface StorageStatus {
  provider: StorageProvider;
  channelName: string;
  connected: boolean;
  ready: boolean;
  details: string;
}

export interface CreateFolderRequest {
  name: string;
  parentId?: string | null;
}

export interface CreateFileRequest {
  name: string;
  parentId?: string | null;
  size?: number;
  mimeType?: string | null;
}

export interface UpdateDriveItemRequest {
  name?: string;
  parentId?: string | null;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}
