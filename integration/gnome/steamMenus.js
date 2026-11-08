import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

// Protocol routes are the real actions shipped in the installed Steam desktop
// entry. Account/help web pages are deliberately labelled as web destinations.
const STEAM_URIS = Object.freeze({
    store: 'steam://store',
    library: 'steam://open/games',
    community: 'steam://url/SteamIDControlPage',
    friends: 'steam://open/friends',
    settings: 'steam://open/settings',
    screenshots: 'steam://open/screenshots',
    news: 'steam://open/news',
    servers: 'steam://open/servers',
    bigPicture: 'steam://open/bigpicture',
});

const SteamMenuButton = GObject.registerClass(
class SteamMenuButton extends PanelMenu.Button {
    _init(title, bold = false) {
        super._init(0.0, title);
        this.add_child(new St.Label({
            text: title, style_class: 'panel-button-label',
            y_align: Clutter.ActorAlign.CENTER,
        }));
        this.add_style_class_name('tahoe-steam-menu-button');
        this.set_style(`-natural-hpadding: 7px; -minimum-hpadding: 5px; font-weight: ${bold ? 'bold' : 'normal'};`);
        this.menu.actor.add_style_class_name('tahoe-system-menu');
    }
});

export class SteamMenus {
    constructor(options = {}) {
        this._onSettings = options.onSettings ?? null;
        this._winePrefix = options.winePrefix ?? GLib.build_filenamev([GLib.get_home_dir(), '.wine']);
        this._wineSteam = options.wineSteam ?? GLib.build_filenamev([
            this._winePrefix, 'drive_c', 'Program Files (x86)', 'Steam', 'steam.exe',
        ]);
        this._tracker = Shell.WindowTracker.get_default();
        this._buttons = [];
        this._nativeRecords = new Map();
        this._client = null;
        this._active = false;
        this._destroyed = false;
        this._syncing = false;
        this._syncIdle = 0;
        this._buildMenus();
        this._focusSignal = global.display.connect('notify::focus-window', () => this._queueSync());
        this._childSignal = Main.panel._leftBox.connect('child-added', () => {
            if (!this._syncing)
                this._queueSync();
        });
        this._queueSync();
    }

    _buildMenus() {
        const definitions = [
            ['Steam', [
                ['About Steam (Web)…', () => this._openWeb('https://store.steampowered.com/about/')],
                null,
                ['Preferences…', () => this._openSteam('settings')],
            ]],
            ['Account', [
                ['Account Details (Web)…', () => this._openWeb('https://store.steampowered.com/account/')],
                ['My Community Profile', () => this._openSteam('community')],
            ]],
            ['View', [
                ['Store', () => this._openSteam('store')],
                ['Library', () => this._openSteam('library')],
                ['Community', () => this._openSteam('community')],
                null,
                ['Screenshots', () => this._openSteam('screenshots')],
                ['News', () => this._openSteam('news')],
                ['Big Picture Mode', () => this._openSteam('bigPicture')],
            ]],
            ['Friends', [
                ['Friends & Chat', () => this._openSteam('friends')],
                ['My Community Profile', () => this._openSteam('community')],
            ]],
            ['Games', [
                ['Game Library', () => this._openSteam('library')],
                ['Steam Store', () => this._openSteam('store')],
                ['Game Servers', () => this._openSteam('servers')],
            ]],
            ['Window', [
                ['Minimize', () => this._windowAction('minimize'), 'minimize'],
                ['Zoom', () => this._windowAction('zoom'), 'zoom'],
                null,
                ['Close Window', () => this._windowAction('close'), 'close'],
            ]],
            ['Help', [
                ['Steam Support (Web)…', () => this._openWeb('https://help.steampowered.com/')],
                ['Steam News', () => this._openSteam('news')],
            ]],
        ];
        if (this._onSettings)
            definitions.at(-1)[1].push(null, ['Desktop Settings…', () => this._onSettings()]);
        this._windowItems = new Map();
        for (const [index, [title, definitionsForMenu]] of definitions.entries()) {
            const button = new SteamMenuButton(title, index === 0);
            for (const definition of definitionsForMenu) {
                if (definition === null) {
                    button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                    continue;
                }
                const [label, callback, windowAction] = definition;
                const item = new PopupMenu.PopupMenuItem(label);
                item.connect('activate', () => this._run(callback));
                button.menu.addMenuItem(item);
                if (windowAction)
                    this._windowItems.set(windowAction, item);
            }
            button.menu.connect('open-state-changed', (_menu, open) => {
                if (open)
                    this._syncWindowItems();
            });
            Main.panel.addToStatusArea(`tahoeSteamMenu${title}`, button, index + 1, 'left');
            button.container.hide();
            this._buttons.push(button);
        }
    }

    _run(callback) {
        try {
            callback();
        } catch (error) {
            console.error(`[tahoe-steam-menu] ${error.message}`);
            Main.notifyError('Steam Menu', 'This Steam command could not be opened.');
        }
    }

    _clientForWindow(window) {
        if (!window)
            return null;
        const wmClass = (window.get_wm_class?.() ?? '').toLowerCase();
        const instance = (window.get_wm_class_instance?.() ?? '').toLowerCase();
        // Games may use a steam_app_<ID> class. They retain their own app menus.
        if (wmClass.startsWith('steam_app_') || instance.startsWith('steam_app_'))
            return null;
        const app = this._tracker.get_window_app(window);
        const id = (app?.get_id() ?? '').toLowerCase();
        const wine = /^(steam|steamwebhelper)\.exe$/.test(wmClass) ||
            /^(steam|steamwebhelper)\.exe$/.test(instance) ||
            (id.startsWith('wine-') && id.includes('steam'));
        const native = ['steam', 'steamwebhelper'].includes(wmClass) ||
            ['steam', 'steamwebhelper'].includes(instance) ||
            ['steam.desktop', 'steam_steam.desktop', 'com.valvesoftware.steam.desktop'].includes(id);
        return wine || native ? {window, wine, appInfo: app?.get_app_info() ?? null} : null;
    }

    _queueSync() {
        if (this._destroyed || this._syncIdle)
            return;
        this._syncIdle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._syncIdle = 0;
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        if (this._destroyed)
            return;
        this._setClient(this._clientForWindow(global.display.focus_window));
    }

    // Kept separate from focus detection so a private compositor can validate
    // menu presentation and restoration without launching or controlling Steam.
    _setClient(client) {
        this._client = client;
        this._active = client !== null;
        this._syncing = true;
        try {
            if (this._active) {
                this._hideNativeMenus();
                const left = Main.panel._leftBox;
                const apple = Main.panel.statusArea.tahoeAppleMenu?.container;
                const start = apple ? left.get_children().indexOf(apple) + 1 : 0;
                this._buttons.forEach((button, index) => {
                    left.set_child_at_index(button.container, start + index);
                    button.container.show();
                });
                this._syncWindowItems();
            } else {
                this._buttons.forEach(button => {
                    button.menu.close();
                    button.container.hide();
                });
                this._restoreNativeMenus();
            }
        } finally {
            this._syncing = false;
        }
    }

    _hideNativeMenus() {
        for (const container of Main.panel._leftBox.get_children()) {
            const button = container.first_child;
            if (!button?._globalMenuButton && !button?._globalMenuAppName)
                continue;
            if (!this._nativeRecords.has(container)) {
                const record = {visible: container.visible, visibleSignal: 0, destroySignal: 0};
                record.visibleSignal = container.connect('notify::visible', () => {
                    if (this._active && container.visible)
                        container.hide();
                });
                record.destroySignal = container.connect('destroy', () => this._nativeRecords.delete(container));
                this._nativeRecords.set(container, record);
            }
            button.menu?.close();
            container.hide();
        }
    }

    _restoreNativeMenus() {
        for (const [container, record] of this._nativeRecords) {
            container.disconnect(record.visibleSignal);
            container.disconnect(record.destroySignal);
            const hiddenByOwner = container.first_child?._globalMenuHidden === true;
            container.visible = record.visible && !hiddenByOwner;
        }
        this._nativeRecords.clear();
    }

    _syncWindowItems() {
        const window = this._client?.window;
        this._windowItems.get('minimize').setSensitive(Boolean(window?.can_minimize?.()));
        this._windowItems.get('zoom').setSensitive(Boolean(window?.can_maximize?.()));
        this._windowItems.get('close').setSensitive(Boolean(window?.can_close?.()));
    }

    _windowAction(action) {
        const window = this._client?.window;
        if (!window)
            return;
        for (const button of this._buttons)
            button.menu.close();
        if (action === 'minimize' && window.can_minimize())
            window.minimize();
        else if (action === 'zoom' && window.can_maximize()) {
            if (window.is_maximized())
                window.unmaximize();
            else
                window.maximize();
        } else if (action === 'close' && window.can_close())
            window.delete(global.get_current_time());
    }

    _openSteam(action) {
        const uri = STEAM_URIS[action];
        const client = this._client;
        if (!uri || !client)
            return;
        if (client.wine) {
            if (!Gio.File.new_for_path(this._wineSteam).query_exists(null))
                throw new Error('Wine Steam executable is unavailable');
            const launcher = new Gio.SubprocessLauncher({
                flags: Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            });
            launcher.setenv('WINEPREFIX', this._winePrefix, true);
            launcher.set_cwd(GLib.path_get_dirname(this._wineSteam));
            launcher.spawnv(['/usr/bin/wine', this._wineSteam, uri]);
        } else if (client.appInfo?.supports_uris()) {
            client.appInfo.launch_uris([uri], global.create_app_launch_context(global.get_current_time(), -1));
        } else {
            this._openWeb(uri);
        }
    }

    _openWeb(uri) {
        Gio.AppInfo.launch_default_for_uri_async(uri, null, null, (_source, result) => {
            try {
                Gio.AppInfo.launch_default_for_uri_finish(result);
            } catch (error) {
                console.error(`[tahoe-steam-menu] ${error.message}`);
                Main.notifyError('Steam Menu', 'This destination could not be opened.');
            }
        });
    }

    destroy() {
        if (this._destroyed)
            return;
        this._destroyed = true;
        if (this._syncIdle)
            GLib.source_remove(this._syncIdle);
        this._syncIdle = 0;
        global.display.disconnect(this._focusSignal);
        Main.panel._leftBox.disconnect(this._childSignal);
        this._active = false;
        this._restoreNativeMenus();
        this._buttons.forEach(button => button.destroy());
        this._buttons = [];
        this._windowItems.clear();
        this._client = null;
    }
}
