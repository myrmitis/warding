/**
 * pet-preload.js — the overlay's only bridge to the main process.
 *
 * Deliberately tiny. The renderer talks to the BACKEND over same-origin HTTP (it is
 * a page served by the gateway, so its cookie is present), which leaves exactly one
 * thing it cannot do for itself: tell the window whether the pointer is currently
 * over the companion, so input can be accepted there and refused everywhere else.
 *
 * `contextIsolation` is on and `nodeIntegration` off, so this is the whole surface —
 * no `require`, no filesystem, no arbitrary IPC.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("deskCompanion", {
  /**
   * Report the companion's and bubble's hitboxes for this window.
   *
   * The window covers the whole display, so leaving input enabled would make the
   * desktop unclickable. Rather than toggle input as the pointer enters and leaves
   * the sprite — which needed an IPC round-trip and let a fast click fall through —
   * the renderer hands the main process the rects and the main process polls the
   * cursor and toggles ignore-mouse itself.
   *
   * @param {{x:number,y:number,w:number,h:number}|null} pet
   * @param {{x:number,y:number,w:number,h:number}|null} bubble
   */
  updateHitbox(pet, bubble) {
    ipcRenderer.send("desk-companion:update-hitbox", pet || null, bubble || null);
  },

  /**
   * Report the context menu's rect while it is open, or null when it closes.
   *
   * Added as one more interactive hitbox so the menu is clickable while the rest of
   * the desktop stays click-through — no more making the whole window interactive
   * for the menu's lifetime.
   *
   * @param {{x:number,y:number,w:number,h:number}|null} rect
   */
  setMenuHitbox(rect) {
    ipcRenderer.send("desk-companion:menu-hitbox", rect || null);
  },

  /**
   * Grant or withdraw keyboard focus for this window.
   *
   * The overlay is created non-focusable on purpose: it covers the whole display and
   * must never steal focus from whatever the user is actually doing. But the panel
   * has a text input, and a non-focusable window cannot receive typing at all.
   *
   * So focus is granted only while the panel is open and withdrawn as soon as it
   * closes — the narrowest window in which the trade-off is worth making. The v1.0
   * spec flags this exact tension as the thing to verify before building the panel.
   *
   * @param {boolean} focusable true while the panel is open
   */
  setFocusable(focusable) {
    ipcRenderer.send("desk-companion:focusable", Boolean(focusable));
  },

  /**
   * Open the panel beside the companion.
   *
   * The companion's rect is passed in SCREEN coordinates because only the renderer
   * knows where inside its full-display overlay the companion currently sits — the
   * main process would have to guess, and would guess wrong the moment it is dragged.
   *
   * @param {{x:number,y:number,width:number,height:number}} petRect
   */
  panelOpen(petRect) {
    ipcRenderer.send("desk-companion:panel-open", petRect);
  },

  panelClose() {
    ipcRenderer.send("desk-companion:panel-close");
  },

  /**
   * Report that the breathing exercise is running, so a click elsewhere does not
   * close the panel and discard it.
   */
  panelBreathing(active) {
    ipcRenderer.send("desk-companion:panel-breathing", Boolean(active));
  },

  /** Report that a destination view is open, for the same reason. */
  panelHold(hold) {
    ipcRenderer.send("desk-companion:panel-hold", Boolean(hold));
  },

  /**
   * The panel window has closed.
   *
   * The companion needs this because the panel can be dismissed without it: a click
   * elsewhere, Escape, or its own ✕. Without it the companion keeps thinking the panel
   * is open, so the next click reads as "close" and it appears dead.
   */
  onPanelClosed(cb) {
    const handler = () => cb();
    ipcRenderer.on("desk-companion:panel-closed", handler);
    return () => ipcRenderer.removeListener("desk-companion:panel-closed", handler);
  },

  /**
   * Open a link in the user's real browser.
   *
   * Must go through the main process: `window.open` from here opens another Electron
   * window, which is not what "open petdex.dev" means.
   */
  openExternal(url) {
    ipcRenderer.send("desk-companion:open-external", url);
  },

  /**
   * Tell every companion overlay the active avatar changed.
   *
   * The gallery is its OWN window, so an in-page notification never reaches the
   * overlay — which is why switching avatars appeared to do nothing until a reload.
   * The main process is the only thing both windows share.
   */
  appearanceChanged() {
    ipcRenderer.send("desk-companion:appearance-changed");
  },

  /** Fires when the active avatar changed, in any window. */
  onAppearanceChanged(cb) {
    const handler = () => cb();
    ipcRenderer.on("desk-companion:appearance-changed", handler);
    return () => ipcRenderer.removeListener("desk-companion:appearance-changed", handler);
  },

  /** Open the avatar gallery. */
  galleryOpen() {
    ipcRenderer.send("desk-companion:gallery-open");
  },

  galleryClose() {
    ipcRenderer.send("desk-companion:gallery-close");
  },

  /**
   * The avatar gallery window opened / closed.
   *
   * The overlay has no other signal — the gallery is its own window — and it needs
   * this to hold the companion still while the user is picking an avatar, then let it
   * wander again once the gallery is gone.
   */
  onGalleryOpened(cb) {
    const handler = () => cb();
    ipcRenderer.on("desk-companion:gallery-opened", handler);
    return () => ipcRenderer.removeListener("desk-companion:gallery-opened", handler);
  },

  onGalleryClosed(cb) {
    const handler = () => cb();
    ipcRenderer.on("desk-companion:gallery-closed", handler);
    return () => ipcRenderer.removeListener("desk-companion:gallery-closed", handler);
  },

  /** Which side the panel opened on, so the card can aim its entry animation. */
  onPanelOpened(cb) {
    const handler = (_e, side) => cb(side);
    ipcRenderer.on("desk-companion:panel-opened", handler);
    return () => ipcRenderer.removeListener("desk-companion:panel-opened", handler);
  },
});
