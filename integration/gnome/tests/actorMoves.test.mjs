import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../actorMoves.js', import.meta.url), 'utf8');
const {ActorMoves} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
class Actor {
    constructor(name) {this.name=name; this.children=[]; this.signals=new Map(); this.next=1; this.parent=null; this.dead=false;}
    live() {assert.equal(this.dead,false,`GI called on disposed ${this.name}`);}
    connect(name,cb) {this.live(); const id=this.next++; this.signals.set(id,{name,cb});return id;}
    disconnect(id) {this.live();assert(this.signals.delete(id));}
    get_parent() {this.live();return this.parent;}
    get_children() {this.live();return [...this.children];}
    get_n_children() {this.live();return this.children.length;}
    add_child(a) {this.insert_child_at_index(a,this.children.length);}
    insert_child_at_index(a,i) {this.live();a.live();assert.equal(a.parent,null);this.children.splice(i,0,a);a.parent=this;}
    remove_child(a) {this.live();a.live();assert.equal(a.parent,this);this.children.splice(this.children.indexOf(a),1);a.parent=null;}
    destroy() {this.live();for(const {name,cb} of [...this.signals.values()])if(name==='destroy')cb();for(const a of [...this.children])a.destroy();if(this.parent)this.parent.remove_child(this);this.dead=true;this.signals.clear();}
}
// Restore ordering after moving several owned actors into temporary UI.
{
 const m=new ActorMoves(), original=new Actor('original'), temp=new Actor('temp');
 const actors=['first','second','third'].map(n=>new Actor(n));actors.forEach(a=>original.add_child(a));
 m.move(actors[0],temp);m.move(actors[2],temp);m.restoreAll();assert.deepEqual(original.children,actors);m.destroy();temp.destroy();assert(actors.every(a=>!a.dead));
}
// Owning extension destroys borrowed indicator first. No disposed wrapper calls.
{
 const m=new ActorMoves(),original=new Actor('owner'),temp=new Actor('temp'),indicator=new Actor('indicator');
 original.add_child(indicator);m.move(indicator,temp);indicator.destroy();original.destroy();m.restoreAll();m.destroy();temp.destroy();
}
// Original container destroyed while its borrowed child survives: detach child.
{
 const m=new ActorMoves(),original=new Actor('owner'),temp=new Actor('temp'),indicator=new Actor('indicator');
 original.add_child(indicator);m.move(indicator,temp);original.destroy();m.restoreAll();temp.destroy();assert.equal(indicator.dead,false);assert.equal(indicator.parent,null);m.destroy();indicator.destroy();
}
// Extension removed and replaced while ours remains enabled.
{
 const m=new ActorMoves(),original=new Actor('owner'),temp=new Actor('temp'),a=new Actor('old');
 original.add_child(a);m.move(a,temp);a.destroy();const b=new Actor('new');original.add_child(b);m.move(b,temp);m.restoreAll();assert.deepEqual(original.children,[b]);m.destroy();
}
console.log('ActorMoves: 4 lifecycle scenarios passed');
