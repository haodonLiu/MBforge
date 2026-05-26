"use strict";

const PREF_BRANCH = "extensions.mbforge-bridge.";

const MBForgeBridge = {
  id: null,
  version: null,
  rootURI: null,
  initialized: false,
  addedElementIDs: [],

  init({ id, version, rootURI }) {
    if (this.initialized) return;
    this.id = id;
    this.version = version;
    this.rootURI = rootURI;
    this.initialized = true;
  },

  // ---------- 配置读写 ----------
  _getHost() {
    return (
      Zotero.Prefs.get(PREF_BRANCH + "host", true) || "http://localhost"
    );
  },

  _getPort() {
    return Zotero.Prefs.get(PREF_BRANCH + "port", true) || 8233;
  },

  _getAutoIndex() {
    return !!Zotero.Prefs.get(PREF_BRANCH + "auto_index", true);
  },

  _apiUrl(path) {
    return `${this._getHost()}:${this._getPort()}${path}`;
  },

  // ---------- UI 注入 ----------
  addToWindow(window) {
    const doc = window.document;

    // 1. Item 右键菜单
    const itemMenu = doc.getElementById("zotero-itemmenu");
    if (itemMenu) {
      const sep = doc.createXULElement("menuseparator");
      sep.id = "mbforge-separator";
      itemMenu.appendChild(sep);
      this.storeAddedElement(sep);

      const mi = doc.createXULElement("menuitem");
      mi.id = "mbforge-push-menuitem";
      mi.setAttribute("label", "推送到 MBForge");
      mi.addEventListener("command", () => this.handlePush());
      itemMenu.appendChild(mi);
      this.storeAddedElement(mi);
    }

    // 2. Collection 右键菜单（推送整个分类）
    const collMenu = doc.getElementById("zotero-collectionmenu");
    if (collMenu) {
      const sep2 = doc.createXULElement("menuseparator");
      sep2.id = "mbforge-coll-separator";
      collMenu.appendChild(sep2);
      this.storeAddedElement(sep2);

      const mi2 = doc.createXULElement("menuitem");
      mi2.id = "mbforge-push-coll-menuitem";
      mi2.setAttribute("label", "推送该分类到 MBForge");
      mi2.addEventListener("command", () => this.handlePushCollection());
      collMenu.appendChild(mi2);
      this.storeAddedElement(mi2);
    }

    // 3. Tools 菜单添加设置入口
    const toolsPopup = doc.getElementById("menu_ToolsPopup");
    if (toolsPopup) {
      const sep3 = doc.createXULElement("menuseparator");
      sep3.id = "mbforge-tools-separator";
      toolsPopup.appendChild(sep3);
      this.storeAddedElement(sep3);

      const mi3 = doc.createXULElement("menuitem");
      mi3.id = "mbforge-settings-menuitem";
      mi3.setAttribute("label", "MBForge Bridge 设置");
      mi3.addEventListener("command", () => this.openSettings(window));
      toolsPopup.appendChild(mi3);
      this.storeAddedElement(mi3);
    }
  },

  addToAllWindows() {
    const windows = Zotero.getMainWindows();
    for (let win of windows) {
      if (!win.ZoteroPane) continue;
      this.addToWindow(win);
    }
  },

  storeAddedElement(elem) {
    if (!elem.id) throw new Error("Element must have an id");
    this.addedElementIDs.push(elem.id);
  },

  removeFromWindow(window) {
    const doc = window.document;
    for (let id of this.addedElementIDs) {
      doc.getElementById(id)?.remove();
    }
  },

  removeFromAllWindows() {
    const windows = Zotero.getMainWindows();
    for (let win of windows) {
      if (!win.ZoteroPane) continue;
      this.removeFromWindow(win);
    }
  },

  // ---------- 设置对话框 ----------
  openSettings(window) {
    const dialog = window.openDialog(
      "data:text/html," + encodeURIComponent(this._settingsHTML()),
      "mbforge-settings",
      "chrome,modal,centerscreen,width=400,height=250",
      {
        host: this._getHost(),
        port: this._getPort(),
        autoIndex: this._getAutoIndex(),
        save: (h, p, a) => {
          Zotero.Prefs.set(PREF_BRANCH + "host", h, true);
          Zotero.Prefs.set(PREF_BRANCH + "port", parseInt(p, 10), true);
          Zotero.Prefs.set(PREF_BRANCH + "auto_index", a, true);
        },
      }
    );
  },

  _settingsHTML() {
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MBForge Bridge 设置</title>
<style>
body{font-family:system-ui,sans-serif;padding:20px;margin:0;background:#f6f7f9}
label{display:block;margin:12px 0 4px;font-size:13px;font-weight:600}
input[type="text"],input[type="number"]{width:100%;padding:6px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}
.actions{margin-top:20px;text-align:right}
button{padding:6px 16px;border-radius:4px;border:none;cursor:pointer}
.btn-primary{background:#4f6ef7;color:#fff}
.btn-cancel{background:#e2e4e9;color:#333;margin-right:8px}
</style></head>
<body>
<h3>MBForge Bridge 设置</h3>
<label>服务地址</label>
<input id="host" type="text" placeholder="http://localhost">
<label>端口</label>
<input id="port" type="number" placeholder="8233">
<label><input id="autoIndex" type="checkbox"> 推送后自动解析索引</label>
<div class="actions">
<button class="btn-cancel" onclick="window.close()">取消</button>
<button class="btn-primary" onclick="save()">保存</button>
</div>
<script>
const args = window.arguments[0];
document.getElementById('host').value = args.host;
document.getElementById('port').value = args.port;
document.getElementById('autoIndex').checked = args.autoIndex;
function save(){
  args.save(
    document.getElementById('host').value,
    document.getElementById('port').value,
    document.getElementById('autoIndex').checked
  );
  window.close();
}
<\/script>
</body></html>`;
  },

  // ---------- 推送逻辑 ----------
  async handlePush() {
    const items = ZoteroPane.getSelectedItems();
    if (!items || items.length === 0) {
      this._alert("请先选中至少一个文献条目。");
      return;
    }
    await this._pushItems(items);
  },

  async handlePushCollection() {
    const collection = ZoteroPane.getSelectedCollection();
    if (!collection) {
      this._alert("请先选中一个分类。");
      return;
    }
    const items = collection.getChildItems(true);
    if (!items || items.length === 0) {
      this._alert("该分类下没有文献条目。");
      return;
    }
    await this._pushItems(items);
  },

  async _pushItems(items) {
    const payloadItems = [];
    for (const item of items) {
      if (!item.isRegularItem()) continue;
      const payload = await this._collectItemData(item);
      if (payload) payloadItems.push(payload);
    }

    if (payloadItems.length === 0) {
      this._alert("选中的条目中未找到可供推送的 PDF 附件。");
      return;
    }

    const url = this._apiUrl("/api/v1/zotero/import");
    const body = JSON.stringify({
      items: payloadItems,
      auto_index: this._getAutoIndex(),
    });

    try {
      const result = await this._httpPost(url, body);
      this._alert(
        `推送成功！共 ${payloadItems.length} 个条目，` +
        `${result.imported || 0} 个已导入 MBForge。`
      );
    } catch (err) {
      Zotero.debug("[MBForge] Push failed: " + err);
      this._alert(
        `推送失败：${err}\n\n` +
        `请确认 MBForge Bridge 服务已启动：\n` +
        `mbforge zotero-bridge --project ./my-project`
      );
    }
  },

  _httpPost(url, body) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch (e) {
            reject("返回数据不是有效 JSON: " + xhr.responseText);
          }
        } else {
          reject(`HTTP ${xhr.status}: ${xhr.responseText}`);
        }
      };
      xhr.onerror = () => reject("网络请求失败，请确认服务已启动");
      xhr.ontimeout = () => reject("请求超时");
      xhr.send(body);
    });
  },

  async _collectItemData(item) {
    const data = {
      key: item.key,
      libraryID: item.libraryID,
      title: item.getField("title") || "",
      authors: this._getAuthors(item),
      abstract: item.getField("abstractNote") || "",
      url: item.getField("url") || "",
      doi: item.getField("DOI") || "",
      date: item.getField("date") || "",
      tags: item.getTags().map((t) => t.tag),
      attachments: [],
      annotations: [],
    };

    const attachmentIDs = item.getAttachments();
    for (const id of attachmentIDs) {
      const attachment = Zotero.Items.get(id);
      if (!attachment) continue;
      if (attachment.isPDFAttachment()) {
        const path = await attachment.getFilePathAsync();
        data.attachments.push({
          id: attachment.key,
          filename: attachment.attachmentFilename || attachment.getDisplayTitle(),
          path: path || "",
          contentType: "application/pdf",
        });

        const annoIDs = attachment.getAnnotations();
        for (const annoID of annoIDs) {
          const anno = Zotero.Items.get(annoID);
          if (!anno) continue;
          data.annotations.push({
            attachmentKey: attachment.key,
            type: anno.annotationType || "unknown",
            page: anno.annotationPageLabel || "",
            text: anno.annotationText || "",
            comment: anno.annotationComment || "",
            color: anno.annotationColor || "",
            position: anno.annotationPosition || null,
          });
        }
      }
    }

    return data.attachments.length > 0 ? data : null;
  },

  _getAuthors(item) {
    const creators = item.getCreators();
    if (!creators || creators.length === 0) return "";
    return creators
      .filter((c) => c.creatorType === "author")
      .map((c) => `${c.firstName || ""} ${c.lastName || ""}`.trim())
      .join(", ");
  },

  _alert(msg) {
    const win = Zotero.getMainWindow();
    if (win && win.Services) {
      win.Services.prompt.alert(win, "MBForge Bridge", msg);
    }
  },
};

// ====================================================================
// Bootstrap 生命周期钩子
// ====================================================================

function startup({ id, version, rootURI }, reason) {
  MBForgeBridge.init({ id, version, rootURI });
  MBForgeBridge.addToAllWindows();

  const windowWatcher = Cc[
    "@mozilla.org/embedcomp/window-watcher;1"
  ].getService(Ci.nsIWindowWatcher);
  const observer = {
    observe(win, topic) {
      if (topic === "domwindowopened") {
        win.addEventListener(
          "load",
          () => {
            if (win.ZoteroPane) MBForgeBridge.addToWindow(win);
          },
          { once: true }
        );
      }
    },
  };
  windowWatcher.registerNotification(observer);
  MBForgeBridge._windowWatcherObserver = observer;
}

function shutdown({ id, version, rootURI }, reason) {
  MBForgeBridge.removeFromAllWindows();
  if (MBForgeBridge._windowWatcherObserver) {
    const windowWatcher = Cc[
      "@mozilla.org/embedcomp/window-watcher;1"
    ].getService(Ci.nsIWindowWatcher);
    windowWatcher.unregisterNotification(MBForgeBridge._windowWatcherObserver);
  }
}

function install(data, reason) {}
function uninstall(data, reason) {}
