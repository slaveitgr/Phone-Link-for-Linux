import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as ParentalControls from 'resource:///org/gnome/shell/misc/parentalControlsManager.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';
import {phoneStatus} from './phoneStatus.js';

const CATEGORIES = [
    ['all', 'All'], ['utilities', 'Utilities'], ['social', 'Social'],
    ['productivity', 'Productivity'], ['media', 'Media'], ['games', 'Games'],
    ['other', 'Other'],
];

const LEGACY_ICON_OVERRIDES = {
    'firefox_firefox.desktop': 'firefox',
    'thunderbird_thunderbird.desktop': 'thunderbird',
    'brave_brave.desktop': 'brave-browser',
    'snap-store_snap-store.desktop': 'snap-store',
    'blender_blender.desktop': 'blender',
};

function fold(text) {
    return (text ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
}

function originalLegacyIcon(info) {
    const declared = info.get_string('Icon') ?? '';
    if (!declared.startsWith('slave-local-'))
        return null;
    for (const directory of ['/var/lib/snapd/desktop/applications', '/usr/share/applications']) {
        try {
            const file = new GLib.KeyFile();
            file.load_from_file(`${directory}/${info.get_id()}`, GLib.KeyFileFlags.NONE);
            const icon = file.get_string('Desktop Entry', 'Icon');
            if (icon && !icon.startsWith('slave-local-'))
                return Gio.icon_new_for_string(icon);
        } catch { /* A user override may have no system counterpart. */ }
    }
    const directory = GLib.build_filenamev([
        GLib.get_home_dir(), '.local', 'share', 'icons', 'Slave-Monochrome', '64x64', 'apps',
    ]);
    for (const suffix of ['svg', 'png']) {
        const file = Gio.File.new_for_path(`${directory}/${declared}.${suffix}`);
        if (file.query_exists(null))
            return new Gio.FileIcon({file});
    }
    return null;
}

function categoryFor(categories) {
    const tags = new Set(categories.split(';'));
    if (tags.has('Game'))
        return 'games';
    if (['AudioVideo', 'Audio', 'Video', 'Graphics', 'Photography'].some(c => tags.has(c)))
        return 'media';
    if (['Network', 'Chat', 'InstantMessaging', 'Email', 'WebBrowser'].some(c => tags.has(c)))
        return 'social';
    if (['Office', 'Development', 'Education', 'Science', 'ProjectManagement'].some(c => tags.has(c)))
        return 'productivity';
    if (['Utility', 'System', 'Settings', 'Accessibility', 'Security',
        'FileManager', 'TerminalEmulator'].some(c => tags.has(c)))
        return 'utilities';
    return 'other';
}

export const ApplicationsOverlay = GObject.registerClass(
class ApplicationsOverlay extends ModalDialog.ModalDialog {
    _init() {
        super._init({styleClass: 'tahoe-applications-dialog', destroyOnClose: false});
        this._system = Shell.AppSystem.get_default();
        this._parental = ParentalControls.getDefault();
        this._catalog = [];
        this._filtered = [];
        this._category = 'all';
        this._searchTimeout = 0;
        this._phonePoll = 0;
        this._installedSignal = this._system.connect('installed-changed', () => {
            this._catalog = [];
            if (this.state === ModalDialog.State.OPENED)
                this._render();
        });

        // Keep existing windows visible. The modal's own event
        // blocker and input grab still prevent interaction outside the card.
        this._lightbox.destroy();
        this._lightbox = null;
        const outside = new Clutter.ClickGesture();
        outside.connect('recognize', () => this.close());
        this._eventBlocker.add_action(outside);

        this.buttonLayout.hide();
        this.contentLayout.add_style_class_name('tahoe-applications-content');
        this._body = new St.BoxLayout({style_class: 'tahoe-applications-body',
            x_expand: true, y_expand: true});
        this.contentLayout.add_child(this._body);
        this._appContent = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-applications-main', x_expand: true, y_expand: true});
        this._body.add_child(this._appContent);
        this._buildHeader();
        this._buildCategories();
        this._gridLayout = new Clutter.GridLayout({column_spacing: 12, row_spacing: 10});
        this._grid = new St.Viewport({
            layout_manager: this._gridLayout,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'tahoe-applications-grid',
        });
        this._scroll = new St.ScrollView({
            child: this._grid, x_expand: true, y_expand: true,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            style_class: 'tahoe-applications-scroll',
        });
        this._appContent.add_child(this._scroll);
        this._empty = new St.Label({
            text: 'No applications found', style_class: 'tahoe-applications-empty',
            x_align: Clutter.ActorAlign.CENTER, visible: false,
        });
        this._appContent.add_child(this._empty);
        this._count = new St.Label({style_class: 'tahoe-applications-count'});
        this._appContent.add_child(this._count);
        this._buildPhonePane();

        const keys = new Clutter.KeyController();
        keys.connect('key-press', () => {
            const [, symbol] = keys.get_key();
            if (symbol === Clutter.KEY_Escape) {
                this.close();
                return Clutter.EVENT_STOP;
            }
            if ((symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter) &&
                global.stage.key_focus === this._entry.clutter_text) {
                if (this._filtered[0])
                    this._launch(this._filtered[0].app);
                return Clutter.EVENT_STOP;
            }
            if (symbol === Clutter.KEY_Down && global.stage.key_focus === this._entry.clutter_text) {
                this._grid.get_children().find(c => c.can_focus)?.grab_key_focus();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this.add_action(keys);
        this.setInitialKeyFocus(this._entry.clutter_text);
        this.connect('closed', () => this._stopPhonePoll());
    }

    _buildHeader() {
        const header = new St.BoxLayout({style_class: 'tahoe-applications-header'});
        header.add_child(new St.Icon({icon_name: 'view-app-grid-symbolic', icon_size: 25}));
        this._entry = new St.Entry({
            hint_text: 'Applications', can_focus: true, x_expand: true,
            style_class: 'tahoe-applications-search',
        });
        this._entry.clutter_text.connect('text-changed', () => {
            if (this._searchTimeout)
                GLib.source_remove(this._searchTimeout);
            this._searchTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, () => {
                this._searchTimeout = 0;
                this._render();
                return GLib.SOURCE_REMOVE;
            });
        });
        header.add_child(this._entry);
        const close = new St.Button({
            child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 17}),
            accessible_name: 'Close Applications', can_focus: true,
            style_class: 'tahoe-applications-close',
        });
        close.connect('clicked', () => this.close());
        header.add_child(close);
        this._appContent.add_child(header);
    }

    _buildCategories() {
        const row = new St.BoxLayout({style_class: 'tahoe-applications-categories'});
        row.layout_manager.homogeneous = true;
        this._categoryButtons = new Map();
        for (const [id, label] of CATEGORIES) {
            const button = new St.Button({
                label, can_focus: true, x_expand: true,
                style_class: 'tahoe-applications-category',
            });
            button.connect('clicked', () => this.setCategory(id));
            this._categoryButtons.set(id, button);
            row.add_child(button);
        }
        this._appContent.add_child(row);
    }

    setCategory(id) {
        if (!this._categoryButtons.has(id))
            return;
        this._category = id;
        for (const [key, button] of this._categoryButtons) {
            if (key === id)
                button.add_style_pseudo_class('checked');
            else
                button.remove_style_pseudo_class('checked');
        }
        this._render();
    }

    _readCatalog() {
        const favorites = global.settings.get_strv('favorite-apps');
        const hasTahoeSettings = this._system.lookup_app('local.mike.TahoeSettings.desktop') !== null;
        const seen = new Set();
        this._catalog = this._system.get_installed()
            .filter(info => {
                const id = info.get_id();
                if (!id || id === 'local.mike.TahoeApplications.desktop' || seen.has(id) ||
                    !info.should_show() || !this._parental.shouldShowApp(info))
                    return false;
                if (hasTahoeSettings && id === 'org.gnome.Settings.desktop')
                    return false;
                seen.add(id);
                return true;
            })
            .map(info => {
                const app = this._system.lookup_app(info.get_id());
                const legacyIcon = (info.get_string('Icon') ?? '').startsWith('slave-local-');
                return {
                    id: info.get_id(), app, name: info.get_display_name() || info.get_name(),
                    iconName: legacyIcon ? LEGACY_ICON_OVERRIDES[info.get_id()] : null,
                    originalIcon: legacyIcon && !LEGACY_ICON_OVERRIDES[info.get_id()]
                        ? originalLegacyIcon(info) : null,
                    category: categoryFor(info.get_categories() ?? ''),
                    search: fold([info.get_display_name(), info.get_generic_name(),
                        info.get_description(), ...(info.get_keywords() ?? []), info.get_id()].join(' ')),
                    favorite: favorites.indexOf(info.get_id()),
                };
            })
            .filter(item => item.app)
            .sort((a, b) => {
                if (a.favorite >= 0 && b.favorite < 0)
                    return -1;
                if (b.favorite >= 0 && a.favorite < 0)
                    return 1;
                if (a.favorite >= 0 && b.favorite >= 0)
                    return a.favorite - b.favorite;
                return a.name.localeCompare(b.name);
            });
    }

    _render() {
        if (!this._catalog.length)
            this._readCatalog();
        const query = fold(this._entry.get_text()).trim();
        const words = query.split(/\s+/).filter(Boolean);
        this._filtered = this._catalog.filter(item =>
            (this._category === 'all' || item.category === this._category) &&
            words.every(word => item.search.includes(word)));
        this._grid.destroy_all_children();
        for (const [index, item] of this._filtered.entries()) {
            const content = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_align: Clutter.ActorAlign.CENTER, style_class: 'tahoe-application-tile-content',
            });
            const icon = item.iconName
                ? new St.Icon({icon_name: item.iconName, icon_size: 60})
                : item.originalIcon
                    ? new St.Icon({gicon: item.originalIcon, icon_size: 60})
                : item.app.create_icon_texture(60);
            icon.x_align = Clutter.ActorAlign.CENTER;
            content.add_child(icon);
            const label = new St.Label({text: item.name, style_class: 'tahoe-application-name'});
            label.clutter_text.line_wrap = true;
            label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
            label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            label.clutter_text.set_line_alignment(Pango.Alignment.CENTER);
            content.add_child(label);
            const button = new St.Button({
                child: content, can_focus: true, accessible_name: item.name,
                style_class: 'tahoe-application-tile', width: this._tileWidth,
            });
            button.connect('clicked', () => this._launch(item.app));
            this._gridLayout.attach(button, index % this._columns, Math.floor(index / this._columns), 1, 1);
        }
        this._empty.visible = this._filtered.length === 0;
        this._scroll.visible = this._filtered.length > 0;
        const count = this._filtered.length;
        this._count.text = `${count} ${count === 1 ? 'application' : 'applications'}`;
        this._scroll.vadjustment.value = 0;
    }

    _launch(app) {
        this.close();
        try {
            app.activate();
        } catch (error) {
            Main.notifyError('Applications', `Could not open ${app.get_name()}: ${error.message}`);
        }
    }

    _openPhoneAction(action) {
        this.close();
        const executable = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'tahoe-phone-link']);
        const app = this._system.lookup_app('tahoe-phone-link.desktop');
        if (app && action === 'open')
            app.activate();
        else if (['open', 'login', 'pair', 'calls', 'clipboard', 'notifications', 'messages', 'photos', 'settings'].includes(action))
            Util.spawn([executable, action]);
    }

    _phoneShortcut(label, icon, action = null) {
        const button = new St.Button({can_focus: Boolean(action), reactive: Boolean(action),
            style_class: `tahoe-phone-shortcut${action ? '' : ' unavailable'}`,
            accessible_name: action ? label : `${label} — not available yet`});
        const row = new St.BoxLayout({style_class: 'tahoe-phone-shortcut-row'});
        row.add_child(new St.Icon({icon_name: icon, icon_size: 18}));
        row.add_child(new St.Label({text: label, y_align: Clutter.ActorAlign.CENTER}));
        button.set_child(row);
        if (action)
            button.connect('clicked', () => this._openPhoneAction(action));
        return button;
    }

    _buildPhonePane() {
        this._phonePane = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-pane', width: 260});
        const heading = new St.BoxLayout({style_class: 'tahoe-phone-heading'});
        heading.add_child(new St.Label({text: 'Your phone', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER}));
        const more = new St.Button({can_focus: true, style_class: 'tahoe-phone-more',
            child: new St.Icon({icon_name: 'view-more-symbolic', icon_size: 17}),
            accessible_name: 'Open Phone Link'});
        more.connect('clicked', () => this._openPhoneAction('settings'));
        heading.add_child(more);
        this._phonePane.add_child(heading);
        this._phonePreview = new St.Bin({width: 64, height: 125,
            x_align: Clutter.ActorAlign.CENTER, visible: false,
            style_class: 'tahoe-phone-real-preview'});
        const deviceCard = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-device-card'});
        deviceCard.add_child(this._phonePreview);
        this._phonePane.add_child(deviceCard);
        this._phoneName = new St.Label({style_class: 'tahoe-phone-name',
            x_align: Clutter.ActorAlign.CENTER});
        this._phoneState = new St.Label({style_class: 'tahoe-phone-state',
            x_align: Clutter.ActorAlign.CENTER});
        this._phoneBattery = new St.Label({style_class: 'tahoe-phone-battery',
            x_align: Clutter.ActorAlign.CENTER});
        this._phoneMessage = new St.Label({style_class: 'tahoe-phone-message'});
        for (const label of [this._phoneName, this._phoneState, this._phoneMessage]) {
            label.clutter_text.line_wrap = true;
            label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        }
        for (const actor of [this._phoneName, this._phoneState, this._phoneBattery])
            deviceCard.add_child(actor);
        const links = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-links'});
        links.add_child(this._phoneShortcut('Messages', 'mail-unread-symbolic', 'messages'));
        this._phoneCallButton = this._phoneShortcut('Calls', 'call-start-symbolic', 'calls');
        links.add_child(this._phoneCallButton);
        links.add_child(this._phoneShortcut('Photos', 'image-x-generic-symbolic', 'photos'));
        this._phonePane.add_child(links);
        const recent = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-recents', y_expand: true});
        recent.add_child(new St.Label({text: 'Recent', style_class: 'tahoe-phone-heading'}));
        const notifications = this._phoneShortcut('Notifications', 'preferences-system-notifications-symbolic', 'notifications');
        this._phoneNotificationCount = new St.Label({style_class: 'tahoe-phone-recent-caption',
            x_align: Clutter.ActorAlign.START});
        const notificationRow = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-recent'});
        notificationRow.add_child(notifications);
        notificationRow.add_child(this._phoneNotificationCount);
        recent.add_child(notificationRow);
        recent.add_child(this._phoneShortcut('Clipboard', 'edit-paste-symbolic', 'clipboard'));
        this._phoneMessage.visible = false;
        this._phonePane.add_child(recent);
        this._phoneActions = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL,
            style_class: 'tahoe-phone-actions'});
        this._phonePane.add_child(this._phoneActions);
        this._body.add_child(this._phonePane);
        this._phoneFile = Gio.File.new_for_path(GLib.build_filenamev([
            GLib.get_user_state_dir(), 'tahoe-phone-link', 'status.json']));
        this._refreshPhone();
    }

    _refreshPhone() {
        let status = null;
        try {
            const info = this._phoneFile.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, null);
            if (info.get_size() <= 65536) {
                const [ok, bytes] = this._phoneFile.load_contents(null);
                if (ok)
                    status = JSON.parse(new TextDecoder().decode(bytes));
            }
        } catch { /* Backend may not have been started or an atomic write is pending. */ }
        const view = phoneStatus(status);
        this._phoneName.text = view.name;
        this._phoneState.text = view.label;
        const wallpaper = status?.device?.wallpaper_path;
        const cache = GLib.build_filenamev([GLib.get_user_state_dir(), 'tahoe-phone-link']);
        const allowed = ['jpg', 'png', 'webp'].map(ext => `${cache}/phone-wallpaper.${ext}`);
        const realImage = allowed.includes(wallpaper) && GLib.file_test(wallpaper, GLib.FileTest.IS_REGULAR);
        this._phonePreview.visible = realImage;
        if (realImage && this._phoneWallpaper !== wallpaper) {
            this._phoneWallpaper = wallpaper;
            this._phonePreview.set_style(`background-image: url("${Gio.File.new_for_path(wallpaper).get_uri()}"); background-size: cover; border-radius: 12px;`);
        }
        const radios = [];
        this._phoneState.text = view.state === 'connected' ? '✓  Connected' : view.label;
        if (view.state === 'connected') {
            if (typeof status?.device?.wifi_enabled === 'boolean')
                radios.push(status.device.wifi_enabled ? 'Wi-Fi' : 'Wi-Fi off');
            if (typeof status?.device?.bluetooth_enabled === 'boolean')
                radios.push(status.device.bluetooth_enabled ? 'Bluetooth' : 'Bluetooth off');
        }
        this._phoneBattery.text = [...radios, view.battery].filter(Boolean).join(' · ');
        this._phoneBattery.clutter_text.line_wrap = true;
        this._phoneBattery.visible = Boolean(this._phoneBattery.text);
        this._phoneMessage.text = view.message;
        this._phoneNotificationCount.text = `${view.notificationCount ?? 0} recent notifications`;
        this._phoneState.set_style_class_name(`tahoe-phone-state${view.state === 'connected' ? ' connected' : ''}`);
        const executable = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'tahoe-phone-link']);
        const available = GLib.file_test(executable, GLib.FileTest.IS_EXECUTABLE);
        this._phoneCallButton.reactive = available;
        this._phoneCallButton.can_focus = available;
        const actionKey = JSON.stringify([available, view.actions]);
        if (this._phoneActionKey === actionKey)
            return;
        this._phoneActionKey = actionKey;
        this._phoneActions.destroy_all_children();
        if (!available)
            return;
        const labels = {login: 'Sign in with Microsoft', pair: 'Pair phone', open: 'Open Phone Link'};
        for (const action of view.actions) {
            const button = new St.Button({label: labels[action], can_focus: true,
                style_class: 'tahoe-phone-action'});
            button.connect('clicked', () => this._openPhoneAction(action));
            this._phoneActions.add_child(button);
        }
    }

    _stopPhonePoll() {
        if (this._phonePoll)
            GLib.source_remove(this._phonePoll);
        this._phonePoll = 0;
    }

    open() {
        if (this.state === ModalDialog.State.OPENED || this.state === ModalDialog.State.OPENING)
            return true;
        const monitor = Main.layoutManager.monitors[global.display.get_current_monitor()];
        const width = Math.min(1120, monitor.width - 70);
        const height = Math.min(660, monitor.height - 130);
        this._phonePane.visible = width >= 850;
        const applicationWidth = width - (this._phonePane.visible ? 296 : 0);
        this._columns = applicationWidth >= 700 ? 5 : applicationWidth >= 520 ? 4 : 3;
        this._tileWidth = Math.floor((applicationWidth - 56 - 12 * (this._columns - 1)) / this._columns);
        this._refreshPhone();
        this._stopPhonePoll();
        this._phonePoll = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._refreshPhone();
            return GLib.SOURCE_CONTINUE;
        });
        this.dialogLayout._dialog.set_size(width, height);
        this._entry.set_text('');
        this._catalog = [];
        this.setCategory('all');
        // Keep existing windows visible behind the floating applications menu.
        Main.overview.hide();
        const opened = super.open();
        if (!opened)
            this._stopPhonePoll();
        return opened;
    }

    toggle() {
        if (this.state === ModalDialog.State.OPENED || this.state === ModalDialog.State.OPENING)
            this.close();
        else
            this.open();
    }

    destroy() {
        this.remove_all_transitions();
        this.popModal();
        if (this._searchTimeout)
            GLib.source_remove(this._searchTimeout);
        this._searchTimeout = 0;
        if (this._installedSignal)
            this._system.disconnect(this._installedSignal);
        this._installedSignal = 0;
        this._stopPhonePoll();
        super.destroy();
    }
});
