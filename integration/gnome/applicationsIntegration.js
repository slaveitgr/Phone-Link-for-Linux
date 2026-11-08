import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const INTERFACE = `<node><interface name="org.gnome.Shell.Extensions.TahoeApplications">
    <method name="GetVersion"><arg type="s" direction="out"/></method>
    <method name="Toggle"/><method name="Show"/><method name="Hide"/>
</interface></node>`;

export class ApplicationsIntegration {
    constructor(overlay) {
        this._overlay = overlay;
        this._active = true;
        this._dockButtons = new Map();
        this._manager = null;
        this._managerSignal = 0;
        this._generation = 0;
        this._a11ySettings = new Gio.Settings({schema_id: 'org.gnome.desktop.a11y.keyboard'});
        // Mutter emits overlay-key only for bare Super; Super+D/L/arrows keep
        // their existing bindings. Lease Shell's original handler reversibly.
        this._nativeOverlayHandler = GObject.signal_handler_find(global.display,
            {signalId: 'overlay-key'});
        if (this._nativeOverlayHandler)
            GObject.signal_handler_block(global.display, this._nativeOverlayHandler);
        this._overlayKeySignal = global.display.connect('overlay-key', () => {
            if (!this._a11ySettings.get_boolean('stickykeys-enable'))
                this.Toggle();
        });
        this._nativeModes = Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW;
        Main.wm.setCustomKeybindingHandler('toggle-application-view',
            this._nativeModes | Shell.ActionMode.SYSTEM_MODAL, () => this.Toggle());
        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._dbus.export(Gio.DBus.session, '/org/gnome/Shell/Extensions/TahoeApplications');
        this._extensionSignal = Main.extensionManager.connect('extension-state-changed',
            () => this._hookDocks());
        this._startupSignal = Main.layoutManager.connect('startup-complete', () => this._hookDocks());
        this._hookDocks();
    }

    GetVersion() {
        return '2-phone-link';
    }

    Toggle() {
        const ownModal = this._overlay._hasModal && Main.modalCount === 1;
        const overviewOnly = Main.actionMode === Shell.ActionMode.OVERVIEW && Main.modalCount <= 1;
        if (Main.modalCount === 0 || ownModal || overviewOnly)
            this._overlay.toggle();
    }

    Show() {
        if (Main.modalCount === 0)
            this._overlay.open();
    }

    Hide() {
        this._overlay.close();
    }

    async _hookDocks() {
        const generation = ++this._generation;
        const extension = Main.extensionManager.lookup('ubuntu-dock@ubuntu.com');
        let manager = null;
        if (extension?.path) {
            try {
                const module = await import(Gio.File.new_for_path(`${extension.path}/extension.js`).get_uri());
                if (!this._active || generation !== this._generation)
                    return;
                manager = module.dockManager ?? null;
            } catch { /* The Ubuntu Dock may be disabled or unavailable. */ }
        }
        if (!this._active || generation !== this._generation)
            return;
        if (manager !== this._manager) {
            if (this._manager && this._managerSignal) {
                try { this._manager.disconnect(this._managerSignal); } catch { /* Already destroyed. */ }
            }
            this._manager = manager;
            this._managerSignal = manager?.connect('docks-ready', () => this._hookDocks()) ?? 0;
        }
        const buttons = new Set((manager?._allDocks ?? [])
            .map(dock => dock.dash?.showAppsButton).filter(button => button?.connect));
        for (const button of this._dockButtons.keys()) {
            if (!buttons.has(button))
                this._unhookButton(button);
        }
        for (const button of buttons) {
            if (this._dockButtons.has(button))
                continue;
            const toggleMode = button.toggle_mode;
            button.toggle_mode = false;
            const click = button.connect('clicked', () => this.Toggle());
            const destroy = button.connect('destroy', () => this._dockButtons.delete(button));
            this._dockButtons.set(button, {toggleMode, click, destroy});
        }
    }

    _unhookButton(button) {
        const record = this._dockButtons.get(button);
        if (!record)
            return;
        button.disconnect(record.click);
        button.disconnect(record.destroy);
        button.toggle_mode = record.toggleMode;
        this._dockButtons.delete(button);
    }

    destroy() {
        this._active = false;
        this._generation++;
        if (this._overlayKeySignal)
            global.display.disconnect(this._overlayKeySignal);
        this._overlayKeySignal = 0;
        if (this._nativeOverlayHandler &&
            GObject.signal_handler_is_connected(global.display, this._nativeOverlayHandler))
            GObject.signal_handler_unblock(global.display, this._nativeOverlayHandler);
        this._nativeOverlayHandler = 0;
        if (this._extensionSignal)
            Main.extensionManager.disconnect(this._extensionSignal);
        if (this._startupSignal)
            Main.layoutManager.disconnect(this._startupSignal);
        if (this._manager && this._managerSignal) {
            try { this._manager.disconnect(this._managerSignal); } catch { /* Already destroyed. */ }
        }
        for (const button of this._dockButtons.keys())
            this._unhookButton(button);
        this._dbus?.unexport();
        this._dbus = null;
        const controls = Main.overview._overview.controls;
        Main.wm.setCustomKeybindingHandler('toggle-application-view', this._nativeModes,
            controls._toggleAppsPage.bind(controls));
        this._overlay = null;
        this._manager = null;
    }
}
