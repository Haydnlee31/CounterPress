"""Reviewed, whole-highlight scripts. Positions reference the recorded action index.

Markers are speech-engine timestamps, not estimated words-per-second timings.
The complete paragraph is synthesized once so phrasing has its full context.
"""
from hashlib import sha256
import json
from xml.sax.saxutils import escape

# (playhead position, English, Mandarin). A shot resolves at index + 0.6.
SCRIPTS = {
 'last-gasp': [
  (0, 'Marlow takes the penalty...', 'Marlow主罚点球……'),
  (.6, 'Saved by Ashford! Marlow is there for the rebound—', 'Ashford扑出！Marlow跟上补射——'),
  (1.6, 'and Ashford stops him again!', '又被Ashford挡住了！'),
  (2, 'Rowan picks it up,', 'Rowan拿到球，'),
  (3, 'and sends Mercer racing down the flank.', '随即交给边路前插的Mercer。'),
  (4, 'Mercer drives forward,', 'Mercer带球向前，'),
  (5, 'then releases Hart into space.', '随即分给前方的Hart。'),
  (6, 'Hart carries it towards the box,', 'Hart带球逼近禁区，'),
  (7, 'and sends the cross over.', '起脚传中！'),
  (8, 'Vale heads it back for Ellis—', 'Vale头球回做，交给Ellis——'),
  (9, 'Ellis hits it!', 'Ellis起脚！'),
  (9.6, "Oh, he's scored! What a counterattack!", '球进了！精彩的反击！'),
 ],
 'one-touch': [
  (0, 'Ellis brings the ball forward, looking for a way through.', 'Ellis带球向前，寻找突破口。'),
  (1, 'He finds Rowan,', '他把球交给Rowan，'),
  (2, 'who moves it on to Vale.', 'Rowan随即传给Vale。'),
  (3, 'Vale slips the return pass through, and Ellis is in!', 'Vale送出直传，Ellis接应，机会来了！'),
  (4, 'Ellis shoots—', 'Ellis射门——'),
  (4.6, 'and scores! A lovely passing move from Eastbridge.', '球进了！Eastbridge打出精彩配合！'),
 ],
 'breakaway': [
  (0, 'West finds Ellis, and Eastbridge are on the move.', 'West传给Ellis，Eastbridge向前推进。'),
  (1, 'Ellis sends Mercer through the middle.', 'Ellis把球交给中路的Mercer。'),
  (2, 'Mercer drives towards the box.', 'Mercer带球直奔禁区。'),
  (3, 'He squares it across to Hart—', '他横传给Hart——'),
  (4, 'Hart goes for goal—', 'Hart射门——'),
  (4.6, 'and finishes! Eastbridge turn defence into attack!', '球进了！Eastbridge反击得手！'),
 ],
 'level-first': [
  (0, 'Blake carries Northport forward,', 'Blake带球，为Northport向前推进，'),
  (2, 'then plays it wide to Marlow.', '随后分给边路的Marlow。'),
  (3, 'Marlow tries to bring it back inside—', 'Marlow想把球传回中路——'),
  (3.8, 'but gives it away!', '但传球失误了！'),
  (4, "Cole takes possession. Here's the chance!", 'Cole拿到球，机会来了！'),
  (5, 'Cole shoots—', 'Cole射门——'),
  (5.6, 'and scores! Eastbridge are level!', '球进了！Eastbridge扳平比分！'),
 ],
 'take-lead': [
  (0, 'Cole gets Eastbridge moving, finding Hart.', 'Cole把球交给Hart，Eastbridge展开进攻。'),
  (1, 'Hart sends it on to Hayes.', 'Hart传给Hayes。'),
  (2, 'Hayes takes a touch,', 'Hayes控住球，'),
  (3, 'then finds Mercer.', '随即传给Mercer。'),
  (4, "Mercer returns it into Hayes's path—", 'Mercer回传，找到前插的Hayes——'),
  (5, 'Hayes shoots—', 'Hayes射门——'),
  (5.6, 'and scores! Eastbridge take the lead!', '球进了！Eastbridge取得领先！'),
 ],
 'level-late': [
  (0, 'Fletcher starts the move, finding Arden in midfield.', 'Fletcher发动进攻，传给中场的Arden。'),
  (1, 'Arden works it wide to Marlow,', 'Arden把球分给边路的Marlow，'),
  (2, 'who brings Stone into the move.', 'Marlow接着找到Stone。'),
  (3, 'Stone finds Lane ahead of him.', 'Stone传给前方的Lane。'),
  (4, 'Lane picks out Fletcher, back in the attack—', 'Lane送出传球，Fletcher再次接应——'),
  (5, 'Fletcher shoots—', 'Fletcher射门——'),
  (5.6, 'and scores! Northport are level again!', '球进了！Northport再次扳平！'),
 ],
}


REVIEWED_SOURCES = {'last-gasp': 'd8d32f92cb117daed90e63e5638b1c6e3dd176cdf2d2a8c5bd45e359e0b255d9', 'one-touch': '8b640b5d5919ce6effc4da45bd620c77e0d2c1430392b466c7a18dc3db203d8d', 'breakaway': '12137f89c4723e5106c9baad5729b32f5e2174ae21fc3e153f44915fcc100f2d', 'level-first': '36fff78e7dd2ff1043884048cfb8fe272f626ec464bb86e160774cac93fbc7e3', 'take-lead': '4b014ab252fb7a2ddece043438305b817e142de8863ce2a04b5047924e94e7e9', 'level-late': 'e0969b13539cfad6466efea6c881050539312c7a0ebba4198160b6ba554849ba'}

def narrative(events, language):
    story=events[0].match_id.removeprefix('showcase-').removesuffix('-v1')
    if story not in SCRIPTS: raise ValueError('Highlight has no reviewed commentary')
    zh=language=='zh-Hans'
    beats=[{'position':position,'text':cn if zh else en} for position,en,cn in SCRIPTS[story]]
    if any(not 0<=b['position']<len(events) for b in beats): raise ValueError('Script does not match source')
    voice='zh-CN-YunjianNeural' if zh else 'en-US-GuyNeural'
    language='zh-CN' if zh else 'en-US'
    # One synthesis and one continuous stream. Style changes follow the game's phases.
    parts=[]; previous_style=None
    for i,beat in enumerate(beats):
        event=events[int(beat['position'])]
        exciting=event.action.kind=='shot'
        style=('sports-commentary-excited' if exciting else 'sports-commentary') if zh else ('excited' if exciting else 'newscast')
        if style!=previous_style:
            if previous_style is not None: parts.append('</mstts:express-as>')
            parts.append(f'<mstts:express-as style="{style}" styledegree="1.15">')
            previous_style=style
        parts.append(f'<bookmark mark="b{i}"/>{escape(beat["text"])}')
    parts.append('</mstts:express-as>')
    ssml=f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{language}"><voice name="{voice}">{" ".join(parts)}</voice></speak>'
    source_hash=sha256(json.dumps([e.model_dump(mode='json') for e in events],sort_keys=True).encode()).hexdigest()
    if REVIEWED_SOURCES[story]!=source_hash: raise ValueError('Source changed; review the narrative before regeneration')
    key=sha256((source_hash+ssml).encode()).hexdigest()
    return {'key':key,'beats':beats,'ssml':ssml,'source_hash':source_hash,'event_count':len(events)}


def validate_asset(asset,script):
    import base64, math
    if asset['key']!=script['key'] or asset['source_hash']!=script['source_hash']: raise ValueError('Stale commentary')
    marks=asset['markers'];duration=asset['duration']
    if len(marks)!=len(script['beats']) or not math.isfinite(duration) or not 0<duration<=120: raise ValueError('Invalid track')
    previous=-1
    for mark,beat in zip(marks,script['beats']):
        if mark['position']!=beat['position'] or mark['text']!=beat['text'] or not math.isfinite(mark['at']) or not previous<mark['at']<duration: raise ValueError('Invalid markers')
        previous=mark['at']
    if len(base64.b64decode(asset['audio'],validate=True)) not in range(100,1_000_001): raise ValueError('Invalid audio')
    return asset
