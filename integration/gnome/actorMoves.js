/** Borrowed Clutter actors may outlive their original parent or their owner.
 * Observe destruction before retaining either endpoint; never call GI on a
 * destroyed wrapper, even inside try/catch (native calls may not throw).
 */
export class ActorMoves {
    constructor() {
        this._tracked = new Map();
        this._moves = new Map();
        this._orders = new Map();
        this._dead = new WeakSet();
    }

    track(actor) {
        if (!actor || this._dead.has(actor))
            return false;
        if (!this._tracked.has(actor)) {
            const id = actor.connect('destroy', () => {
                this._dead.add(actor);
                this._tracked.delete(actor);
                this._moves.delete(actor);
                this._orders.delete(actor);
                // Records for surviving children still retain this parent's
                // lifetime marker until they can be detached safely.
            });
            this._tracked.set(actor, id);
        }
        return true;
    }

    isAlive(actor) {
        return Boolean(actor) && !this._dead.has(actor);
    }

    move(actor, destination) {
        if (!this.track(actor) || !this.track(destination))
            return false;
        const parent = actor.get_parent();
        if (!parent || !this.track(parent))
            return false;
        if (!this._orders.has(parent))
            this._orders.set(parent, parent.get_children());
        if (!this._moves.has(actor)) {
            const original = this._orders.get(parent).indexOf(actor);
            this._moves.set(actor, {parent, index: original < 0
                ? parent.get_children().indexOf(actor) : original});
        }
        if (parent !== destination) {
            parent.remove_child(actor);
            if (!this.isAlive(actor) || !this.isAlive(destination))
                return false;
            destination.add_child(actor);
        }
        return true;
    }

    restore(actor) {
        const record = this._moves.get(actor);
        if (!record)
            return;
        this._moves.delete(actor);
        if (!this.isAlive(actor))
            return;
        const parent = actor.get_parent();
        if (parent === record.parent)
            return;
        parent?.remove_child(actor);
        if (!this.isAlive(actor) || !this.isAlive(record.parent))
            return; // Orphan stays detached; do not destroy another owner's actor.
        record.parent.insert_child_at_index(actor,
            Math.min(record.index, record.parent.get_n_children()));
    }

    restoreAll() {
        for (const actor of [...this._moves.keys()])
            this.restore(actor);
    }

    destroy() {
        this.restoreAll();
        for (const [actor, id] of this._tracked)
            actor.disconnect(id);
        this._tracked.clear();
        this._orders.clear();
    }
}
