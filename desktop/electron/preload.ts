import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("jarves", {
  platform: process.platform,
  versions: process.versions,
  send: (channel: string, payload: unknown) => ipcRenderer.send(channel, payload),
});

export {};
