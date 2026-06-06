/**
 * Managed WebSocket connection to AmMeeting backend.
 * Handles reconnection with exponential back-off.
 * Runs in the side panel (not service worker, which can't hold long connections).
 */
import type { ProxyEvent } from "./types";

type WSStatus = "disconnected" | "connecting" | "connected" | "error";

interface WSManagerOptions {
  onEvent: (event: ProxyEvent) => void;
  onStatusChange: (status: WSStatus) => void;
  onRawMessage?: (data: unknown) => void;
}

export class WSManager {
  private ws: WebSocket | null = null;
  private _status: WSStatus = "disconnected";
  private _reconnectDelay = 1000;
  private _maxDelay = 30000;
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _intentionalClose = false;
  private _meetingId: string | null = null;
  private _wsUrl: string | null = null;

  constructor(private opts: WSManagerOptions) {}

  get status(): WSStatus {
    return this._status;
  }

  connect(wsUrl: string, meetingId: string) {
    if (this.ws?.readyState === WebSocket.OPEN && this._meetingId === meetingId) return;

    this._intentionalClose = false;
    this._meetingId = meetingId;
    this._wsUrl = wsUrl;
    this._reconnectDelay = 1000;
    this._doConnect();
  }

  private _doConnect() {
    if (!this._wsUrl) return;
    this._setStatus("connecting");

    const ws = new WebSocket(this._wsUrl);
    this.ws = ws;

    ws.onopen = () => {
      this._reconnectDelay = 1000;
      this._setStatus("connected");
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string) as ProxyEvent;
        this.opts.onEvent(data);
        this.opts.onRawMessage?.(data);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onerror = () => {
      this._setStatus("error");
    };

    ws.onclose = () => {
      this._setStatus("disconnected");
      if (!this._intentionalClose) {
        // Reconnect with exponential back-off
        this._reconnectTimer = setTimeout(() => {
          this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxDelay);
          this._doConnect();
        }, this._reconnectDelay);
      }
    };
  }

  /** Send a JSON message to the backend via WebSocket. */
  send(data: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect() {
    this._intentionalClose = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this._setStatus("disconnected");
    this._meetingId = null;
  }

  private _setStatus(s: WSStatus) {
    if (this._status !== s) {
      this._status = s;
      this.opts.onStatusChange(s);
    }
  }
}
