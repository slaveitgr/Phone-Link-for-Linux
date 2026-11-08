import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {ApplicationsOverlay} from './applicationsOverlay.js';
import {ApplicationsIntegration} from './applicationsIntegration.js';
import {MacTopBar} from './macTopBar.js';
import {SteamMenus} from './steamMenus.js';

const TahoeSystemMenu = GObject.registerClass(
class TahoeSystemMenu extends PanelMenu.Button {
    _init(extensionPath, showApplications) {
        super._init(0.0, 'Apple system menu');
        this.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(`${extensionPath}/apple-symbolic.svg`),
            icon_size: 24,
            style_class: 'system-status-icon tahoe-apple-icon',
        }));
        this.menu.actor.add_style_class_name('tahoe-system-menu');
        this._actions = SystemActions.getDefault();
        this._privacy = new Gio.Settings({schema_id: 'org.gnome.desktop.privacy'});

        this._item('About This Computer', 'computer-symbolic',
            () => Util.spawn([GLib.build_filenamev([
                GLib.get_home_dir(), '.local', 'bin', 'tahoe-about-this-computer',
            ])]));
        this._separator();
        this._item('System Settings…', 'emblem-system-symbolic',
            () => Util.spawn([GLib.build_filenamev([
                GLib.get_home_dir(), '.local', 'bin', 'tahoe-system-settings',
            ])]));
        this._item('App Center…', 'system-software-install-symbolic',
            () => this._appCenter());
        this._item('Applications…', 'view-app-grid-symbolic', showApplications);
        this._separator();
        this._recent = new PopupMenu.PopupSubMenuMenuItem('Recent Items', true);
        this._recent.icon.icon_name = 'document-open-recent-symbolic';
        this.menu.addMenuItem(this._recent);
        this._separator();
        this._item('Force Quit…', 'window-close-symbolic', () => this._forceQuit());
        this._separator();
        this._suspend = this._item('Sleep', 'weather-clear-night-symbolic',
            () => this._actions.activateSuspend());
        this._restart = this._item('Restart…', 'system-reboot-symbolic',
            () => this._actions.activateRestart());
        this._shutdown = this._item('Shut Down…', 'system-shutdown-symbolic',
            () => this._actions.activatePowerOff());
        this._separator();
        this._lock = this._item('Lock Screen', 'system-lock-screen-symbolic',
            () => this._actions.activateLockScreen());
        this._logout = this._item('Log Out…', 'system-log-out-symbolic',
            () => this._actions.activateLogout());

        this._actionSignals = [
            'can-suspend', 'can-restart', 'can-power-off', 'can-lock-screen', 'can-logout',
        ].map(name => this._actions.connect(`notify::${name}`, () => this._syncActions()));
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open) {
                this._actions.forceUpdate();
                this._syncActions();
                this._refreshRecent();
            }
        });
        this._syncActions();
        this._refreshRecent();
    }

    _item(label, iconName, callback) {
        const item = new PopupMenu.PopupImageMenuItem(label, iconName);
        item.connect('activate', () => {
            try {
                callback();
            } catch (error) {
                console.error(`[tahoe-system-menu] ${label}: ${error.message}`);
                Main.notifyError('Apple Menu', `Could not open ${label.replace('…', '')}.`);
            }
        });
        this.menu.addMenuItem(item);
        return item;
    }

    _separator() {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
    }

    _syncActions() {
        this._suspend.setSensitive(this._actions.canSuspend);
        this._restart.setSensitive(this._actions.canRestart);
        this._shutdown.setSensitive(this._actions.canPowerOff);
        this._lock.setSensitive(this._actions.canLockScreen);
        this._logout.setSensitive(this._actions.canLogout);
    }

    _appCenter() {
        const system = Shell.AppSystem.get_default();
        const app = system.lookup_app('snap-store_snap-store.desktop') ??
            system.lookup_app('org.gnome.Software.desktop');
        if (app)
            app.activate();
        else
            Gio.AppInfo.launch_default_for_uri_async('appstream://', null, null, null);
    }

    _forceQuit() {
        // Reuse the existing Wayland-capable window selector. It only starts
        // after the user explicitly selects Force Quit from this menu.
        Gio.DBus.session.call(
            'org.gnome.Shell', '/org/gnome/Shell/Extensions/ForceQuit',
            'org.gnome.Shell.Extensions.ForceQuit', 'SelectWindow',
            null, null, Gio.DBusCallFlags.NONE, 3000, null,
            (connection, result) => {
                try {
                    connection.call_finish(result);
                } catch {
                    Shell.AppSystem.get_default()
                        .lookup_app('org.gnome.SystemMonitor.desktop')?.activate();
                }
            });
    }

    _refreshRecent() {
        this._recent.menu.removeAll();
        if (!this._privacy.get_boolean('remember-recent-files')) {
            this._recentEmpty('Recent history is disabled');
            return;
        }
        const bookmarks = new GLib.BookmarkFile();
        let entries = [];
        try {
            bookmarks.load_from_file(GLib.build_filenamev([
                GLib.get_user_data_dir(), 'recently-used.xbel',
            ]));
            entries = bookmarks.get_uris()
                .filter(uri => uri.startsWith('file://'))
                .filter(uri => {
                    try {
                        return !bookmarks.get_is_private(uri);
                    } catch {
                        return true;
                    }
                })
                .map(uri => {
                    let modified = 0;
                    try {
                        modified = bookmarks.get_modified_date_time(uri).to_unix();
                    } catch { /* A bookmark may not have a timestamp. */ }
                    return {uri, modified};
                })
                .sort((a, b) => b.modified - a.modified)
                .slice(0, 10);
        } catch { /* An empty or absent history is normal. */ }
        if (entries.length === 0) {
            this._recentEmpty('No Recent Items');
            return;
        }
        for (const {uri} of entries) {
            let title;
            try {
                title = bookmarks.get_title(uri);
            } catch { /* Fall back to the local file name. */ }
            title ||= Gio.File.new_for_uri(uri).get_basename() || 'Document';
            const item = new PopupMenu.PopupMenuItem(title);
            item.label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            item.label.style = 'max-width: 26em;';
            item.connect('activate', () => {
                Gio.AppInfo.launch_default_for_uri_async(uri, null, null,
                    (_source, result) => {
                        try {
                            Gio.AppInfo.launch_default_for_uri_finish(result);
                        } catch {
                            Main.notifyError('Recent Items', 'This document could not be opened.');
                        }
                    });
            });
            this._recent.menu.addMenuItem(item);
        }
    }

    _recentEmpty(label) {
        this._recent.menu.addMenuItem(new PopupMenu.PopupMenuItem(label, {reactive: false}));
    }

    destroy() {
        for (const id of this._actionSignals ?? [])
            this._actions.disconnect(id);
        this._actionSignals = [];
        this._privacy = null;
        super.destroy();
    }
});

export default class TahoeSystemMenuExtension extends Extension {
    enable() {
        this._applications = new ApplicationsOverlay();
        this._applicationsIntegration = new ApplicationsIntegration(this._applications);
        this._button = new TahoeSystemMenu(this.path,
            () => {
                this._button.menu.close();
                this._applicationsIntegration.Show();
            });
        Main.panel.addToStatusArea('tahoeAppleMenu', this._button, 0, 'left');
        this._desktopSettings = this.getSettings();
        this._macTopBar = new MacTopBar({
            settings: this._desktopSettings,
            onSearch: () => {
                Main.panel.statusArea.quickSettings?.menu.close();
                this._macTopBar?._battery?.menu.close();
                this._applicationsIntegration.Toggle();
            },
            onSettings: page => {
                if (page === 'power')
                    Util.spawn(['gnome-control-center', 'power']);
                else
                    Util.spawn([GLib.build_filenamev([
                        GLib.get_home_dir(), '.local', 'bin', 'tahoe-system-settings',
                    ]), '--page', page]);
            },
        });
        this._steamMenus = new SteamMenus({
            onSettings: () => Util.spawn([GLib.build_filenamev([
                GLib.get_home_dir(), '.local', 'bin', 'tahoe-system-settings',
            ])]),
        });
        this._activities = Main.panel.statusArea.activities?.container ?? null;
        this._activitiesWereVisible = this._activities?.visible ?? false;
        if (this._activities) {
            this._activitiesSignal = this._activities.connect('notify::visible', () => {
                if (this._activities?.visible)
                    this._activities.hide();
            });
            this._activities.hide();
        }
    }

    disable() {
        this._steamMenus?.destroy();
        this._steamMenus = null;
        this._macTopBar?.destroy();
        this._macTopBar = null;
        this._desktopSettings = null;
        this._applicationsIntegration?.destroy();
        this._applicationsIntegration = null;
        this._applications?.destroy();
        this._applications = null;
        if (this._activitiesSignal)
            this._activities?.disconnect(this._activitiesSignal);
        this._activitiesSignal = 0;
        if (this._activitiesWereVisible)
            this._activities?.show();
        this._activities = null;
        this._button?.destroy();
        this._button = null;
    }
}
