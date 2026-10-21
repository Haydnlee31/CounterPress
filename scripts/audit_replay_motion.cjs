// Deterministic whole-match physical audit. Inputs exported from the local GI reader.
const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path'),{execFileSync}=require('node:child_process');
fs.mkdirSync('var/replay-review',{recursive:true});
require('../frontend/node_modules/esbuild').buildSync({entryPoints:['frontend/src/gi/replay.ts'],bundle:true,platform:'node',format:'cjs',outfile:'var/replay-review/replay-audit.cjs'});
const r=require('../var/replay-review/replay-audit.cjs');
const results=[];
for(const id of ['wyscout-2058017','wyscout-2058007','synthetic-32fe41c5d304ce68d7d9']){
 const m=JSON.parse(execFileSync(path.resolve('.venv/bin/python'),['-c',`from pathlib import Path; from counterpress.gi.service import read_match; print(read_match(Path('fixtures/gi'),'${id}').model_dump_json())`],{env:{...process.env,PYTHONPATH:'backend'},maxBuffer:8*1024*1024}));
 const t=r.playTimeline(r.positionedActions(m.events,4418),m.players,4418);
 let maxPlayer=0,maxBall=0,maxAcceleration=0,previous=null,steps=0;const violations=[],rosterChanges=[];let lastRoster='';
 for(let at=0;at<t.duration;at+=100){
  const group=t.groups.find(g=>at>=g.at&&at<g.at+g.duration),event=group.actions.at(-1).event;
  const roster=r.sceneRoster(m.players,[],event),frame=r.replayFrame(t,at,roster,4418);
  assert.equal(roster.length,22);assert.equal(roster.filter(p=>p.role==='GK').length,2);
  const ids=roster.map(p=>p.player_id).join();if(lastRoster&&lastRoster!==ids)rosterChanges.push({at,event:event.event_id});lastRoster=ids;
  const velocities=new Map();
  if(previous&&previous.scene===group.scene){
   const ball=Math.hypot(frame.ball.x-previous.frame.ball.x,frame.ball.y-previous.frame.ball.y)*10;maxBall=Math.max(maxBall,ball);
   for(const p of frame.players){const q=previous.frame.players.find(q=>q.player_id===p.player_id);if(!q)continue;
    const v={x:(p.x-q.x)*10,y:(p.y-q.y)*10},speed=Math.hypot(v.x,v.y);velocities.set(p.player_id,v);maxPlayer=Math.max(maxPlayer,speed);
    const old=previous.velocities.get(p.player_id);if(old){const a=Math.hypot(v.x-old.x,v.y-old.y)*10;maxAcceleration=Math.max(maxAcceleration,a);if(a>5.05)violations.push({type:'acceleration',value:a,at,player:p.alias_id,event:event.event_id});}
    if(speed>8.05)violations.push({type:'player speed',value:speed,at,player:p.alias_id,event:event.event_id});
   }
   if(ball>32.1)violations.push({type:'ball speed',value:ball,at,event:event.event_id});
  }
  previous={frame,scene:group.scene,velocities};steps++;
 }
 const goals=[4418,9598].map(team=>t.actions.filter(a=>a.event.goal_for===team).length);assert.deepEqual(goals,m.teams.map(team=>team.score));
 results.push({id,minutes:t.duration/60000,scenes:t.groups.at(-1).scene+1,steps,maxPlayer,maxBall,maxAcceleration,goals,rosterChanges:rosterChanges.length,violationCount:violations.length,examples:violations.slice(0,8)});
 console.log(JSON.stringify(results.at(-1)));
}
fs.writeFileSync('var/replay-review/motion-audit.json',JSON.stringify(results,null,2));
if(results.some(r=>r.violationCount))process.exitCode=1;
