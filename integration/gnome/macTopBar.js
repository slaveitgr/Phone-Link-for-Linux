import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import UPower from 'gi://UPowerGlib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';
import {ActorMoves} from './actorMoves.js';

const DEFAULTS = {
    'show-wifi': true,
    'show-battery': true,
    'show-search': true,
    'show-control-center': true,
    'show-system-monitor': false,
    'show-force-quit': false,
};

const StandaloneButton = GObject.registerClass(
class TahoeStandaloneButton extends PanelMenu.Button {
    _init(name, callback = null, realMenu = false) {
        super._init(0.0, name, !realMenu);
        this.add_style_class_name('tahoe-status-button');
        if (callback) {
            const click = new Clutter.ClickGesture();
            click.set_recognize_on_press(true);
            click.connect('recognize', callback);
            this.add_action(click);
            const keys = new Clutter.KeyController();
            keys.connect('key-press', () => {
                const [, symbol] = keys.get_key();
                if (symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter ||
                    symbol === Clutter.KEY_space) {
                    callback();
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });
            this.add_action(keys);
        }
    }
});

/** Reuses GNOME's live native status actors; never replaces the panel/menu. */
export class MacTopBar {
    constructor(options = {}) {
        this._options = options;
        this._settings = options.settings ?? null;
        this._active = true;
        this._signals = [];
        this._actors = new ActorMoves();
        this._buttons = [];
        this._retry = 0;
        this._submenuLater = 0;
        this._ready = false;
        this._quick = Main.panel.statusArea.quickSettings;

        // Hidden storage preserves native actors and their own visibility
        // bindings. Restore them before destroying this bin on disable.
        this._holding = new St.BoxLayout({visible: false});
        Main.uiGroup.add_child(this._holding);
        this._actors.track(this._holding);

        this._wifi = new StandaloneButton('Wi-Fi', () => this._openNetwork());
        this._wifiBox = new St.BoxLayout({style_class: 'panel-status-indicators-box'});
        this._wifi.add_child(this._wifiBox);
        this._offlineWifi = new St.Icon({
            icon_name: 'network-wireless-offline-symbolic',
            style_class: 'system-status-icon', icon_size: 17,
        });
        this._wifiBox.add_child(this._offlineWifi);
        this._addBeforeControlCenter('tahoeWiFi', this._wifi);

        this._battery = new StandaloneButton('Battery', null, true);
        this._batteryBox = new St.BoxLayout({style_class: 'panel-status-indicators-box'});
        this._battery.add_child(this._batteryBox);
        this._batteryTitle = new PopupMenu.PopupMenuItem('Battery', {reactive: false});
        this._battery.menu.addMenuItem(this._batteryTitle);
        this._batteryState = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._battery.menu.addMenuItem(this._batteryState);
        this._battery.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const powerSettings = new PopupMenu.PopupImageMenuItem('Battery Settings…', 'battery-symbolic');
        powerSettings.connect('activate', () => {
            if (this._options.onSettings)
                this._options.onSettings('power');
            else
                Util.spawn(['gnome-control-center', 'power']);
        });
        this._battery.menu.addMenuItem(powerSettings);
        this._battery.menu.connect('open-state-changed', (_menu, open) => {
            if (open)
                this._syncNativeState();
        });
        this._addBeforeControlCenter('tahoeBattery', this._battery);

        this._search = new StandaloneButton('Search Applications', () => this._options.onSearch?.());
        this._search.add_child(new St.Icon({
            icon_name: 'edit-find-symbolic', icon_size: 17, style_class: 'system-status-icon',
        }));
        this._addBeforeControlCenter('tahoeSpotlight', this._search);

        const iconFile = Gio.File.new_for_uri(import.meta.url).get_parent()
            .get_child('control-center-symbolic.svg');
        this._controlCenter = new St.Icon({
            gicon: new Gio.FileIcon({file: iconFile}),
            icon_size: 20, style_class: 'system-status-icon tahoe-control-center-icon',
        });
        this._actors.track(this._controlCenter);
        this._quick?._indicators.add_child(this._controlCenter);
        if (this._quick) {
            this._oldQuickName = this._quick.accessible_name;
            this._quick.accessible_name = 'Control Center';
        }

        if (this._settings)
            this._watch(this._settings, 'changed', () => this._syncSettings());
        this._watch(Main.extensionManager, 'extension-state-changed', () => {
            this._configureNative();
            this._syncClutter();
        });
        this._watch(Main.layoutManager, 'startup-complete', () => this._configureNative());
        this._configureNative();
        if (!this._ready) {
            let attempts = 0;
            this._retry = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
                this._configureNative();
                if (this._ready || !this._active || ++attempts >= 100) {
                    this._retry = 0;
                    return GLib.SOURCE_REMOVE;
                }
                return GLib.SOURCE_CONTINUE;
            });
        }
        this._syncSettings();
    }

    _enabled(key) {
        try {
            return this._settings?.get_boolean(key) ?? DEFAULTS[key];
        } catch {
            return DEFAULTS[key];
        }
    }

    _watch(object, signal, callback) {
        if (!object)
            return;
        if (object instanceof Clutter.Actor && !this._actors.track(object))
            return;
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _addBeforeControlCenter(role, button) {
        const children = Main.panel._rightBox.get_children();
        const index = children.indexOf(this._quick?.container);
        Main.panel.addToStatusArea(role, button, Math.max(0, index), 'right');
        this._buttons.push(button);
        this._actors.track(button);
    }

    _move(actor, destination) {
        return this._actors.move(actor, destination);
    }

    _restore(actor) {
        this._actors.restore(actor);
    }

    _configureNative() {
        if (!this._active || this._ready || !this._quick?._system)
            return;
        this._system = this._quick._system;
        this._network = this._quick._network;
        this._powerToggle = this._system._systemItem.powerToggle;
        const nativeBox = this._quick._indicators;
        this._nativeBox = nativeBox;
        this._actors.track(nativeBox);
        this._actors.track(this._quick.container);
        this._nativeOrder = nativeBox.get_children().filter(actor => actor !== this._controlCenter);
        for (const actor of this._nativeOrder)
            this._actors.track(actor);
        if (this._network?.get_parent() === nativeBox)
            this._move(this._network, this._wifiBox);
        if (this._system.get_parent() === nativeBox)
            this._move(this._system, this._batteryBox);

        // Privacy indicators and unknown extension indicators stay native.
        // Keep _brightness in place: addExternalIndicator uses it as an anchor.
        for (const name of ['_volumeOutput', '_bluetooth', '_powerProfiles',
            '_nightLight', '_darkMode', '_doNotDisturb', '_backlight',
            '_rfkill', '_autoRotate', '_thunderbolt']) {
            const actor = this._quick[name];
            if (actor?.get_parent() === nativeBox)
                this._move(actor, this._holding);
        }
        for (const signal of ['notify::visible', 'notify::title', 'notify::gicon'])
            this._watch(this._powerToggle, signal, () => this._syncNativeState());
        this._watch(this._powerToggle._proxy, 'g-properties-changed', () => this._syncNativeState());
        if (this._network) {
            this._watch(this._network, 'notify::visible', () => this._syncNativeState());
            this._watch(this._network._primaryIndicator, 'notify::visible', () => this._syncNativeState());
            const toggle = this._network._wirelessToggle;
            for (const signal of ['notify::visible', 'notify::checked', 'notify::subtitle'])
                this._watch(toggle, signal, () => this._syncNativeState());
        }
        this._ready = true;
        this._syncNativeState();
        this._syncClutter();
    }

    _syncSettings() {
        if (!this._active)
            return;
        this._search.container.visible = this._enabled('show-search');
        this._controlCenter.visible = this._enabled('show-control-center');
        this._syncNativeState();
        this._syncClutter();
    }

    _syncClutter() {
        for (const [role, key] of [
            ['system-monitor@gnome-shell-extensions.gcampax.github.com', 'show-system-monitor'],
            ['ForceQuitButton', 'show-force-quit'],
        ]) {
            const actor = Main.panel.statusArea[role]?.container;
            if (!actor || !this._actors.track(actor))
                continue;
            if (this._enabled(key))
                this._restore(actor);
            else if (actor.get_parent() !== this._holding)
                this._move(actor, this._holding);
        }
    }

    _syncNativeState() {
        const wireless = this._network?._wirelessToggle;
        const hasPrimary = this._network?._primaryIndicator.visible ?? false;
        const hasVpn = this._network?._vpnIndicator.visible ?? false;
        const hasWireless = wireless?.visible ?? false;
        this._offlineWifi.visible = !hasPrimary && !hasVpn && hasWireless;
        this._offlineWifi.icon_name = wireless?.checked
            ? 'network-wireless-offline-symbolic' : 'network-wireless-disabled-symbolic';
        this._wifi.container.visible = this._enabled('show-wifi') &&
            (this._network?.visible ?? false) && (hasPrimary || hasVpn || hasWireless);
        this._wifi.accessible_name = wireless?.subtitle
            ? `Wi-Fi — ${wireless.subtitle}` : 'Wi-Fi';
        this._battery.container.visible = this._enabled('show-battery') &&
            (this._powerToggle?.visible ?? false);
        if (!this._powerToggle)
            return;
        const percentage = this._powerToggle.title ?? '';
        const state = this._powerToggle._proxy?.State;
        let stateText = 'On Battery';
        if (state === UPower.DeviceState.CHARGING)
            stateText = 'Charging';
        else if (state === UPower.DeviceState.FULLY_CHARGED)
            stateText = 'Fully Charged';
        else if (state === UPower.DeviceState.PENDING_CHARGE)
            stateText = 'Connected to Power';
        this._battery.accessible_name = `Battery ${percentage} — ${stateText}`;
        this._batteryTitle.label.text = `Battery ${percentage}`;
        this._batteryState.label.text = stateText;
    }

    _openNetwork() {
        if (!this._active)
            return;
        Main.overview.hide();
        this._quick.menu.open();
        if (this._submenuLater)
            GLib.source_remove(this._submenuLater);
        this._submenuLater = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._submenuLater = 0;
            if (this._active && this._quick.menu.isOpen) {
                const wireless = this._network?._wirelessToggle;
                const toggle = wireless?.visible ? wireless : this._network?._wiredToggle;
                if (toggle?.visible && toggle.menuEnabled)
                    toggle.menu.open();
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        this._active = false;
        if (this._retry)
            GLib.source_remove(this._retry);
        if (this._submenuLater)
            GLib.source_remove(this._submenuLater);
        this._retry = this._submenuLater = 0;
        for (const [object, id] of this._signals) {
            if (!(object instanceof Clutter.Actor) || this._actors.isAlive(object))
                object.disconnect(id);
        }
        this._signals = [];
        if (this._actors.isAlive(this._quick?.container))
            this._quick.menu.close();
        // Children must be restored BEFORE their temporary parents are destroyed.
        this._actors.restoreAll();
        if (this._actors.isAlive(this._nativeBox) && this._nativeOrder) {
            const known = new Set(this._nativeOrder);
            const restored = this._nativeOrder.filter(actor => {
                return this._actors.isAlive(actor) && actor.get_parent() === this._nativeBox;
            });
            const added = this._nativeBox.get_children().filter(actor =>
                !known.has(actor) && actor !== this._controlCenter);
            const anchor = restored.indexOf(this._quick._brightness);
            restored.splice(anchor < 0 ? restored.length : anchor, 0, ...added);
            restored.forEach((actor, index) => this._nativeBox.set_child_at_index(actor, index));
        }
        if (this._actors.isAlive(this._controlCenter))
            this._controlCenter.destroy();
        if (this._actors.isAlive(this._quick?.container) && this._oldQuickName !== undefined)
            this._quick.accessible_name = this._oldQuickName;
        for (const button of this._buttons) {
            if (this._actors.isAlive(button))
                button.destroy();
        }
        this._buttons = [];
        if (this._actors.isAlive(this._holding))
            this._holding.destroy();
        this._actors.destroy();
        this._settings = null;
        this._options = null;
    }
}
