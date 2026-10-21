"""Extract minimal, attributed lineup metadata from the licensed Wyscout archive."""
import argparse
import hashlib
import json
from pathlib import Path


def prepare(matches_path: Path, players_path: Path, root: Path):
    matches = {m['wyId']: m for m in json.loads(matches_path.read_text())}
    roles = {p['wyId']: p['role']['code2'] for p in json.loads(players_path.read_text())}
    for mid, folder, mapping in [(2058017, root, {4418:4418,9598:9598}),
                                  (2058007, root/'comeback', {5629:4418,12913:9598})]:
        aliases = json.loads((folder/'aliases.json').read_text())
        teams = []
        for source_id, team_id in mapping.items():
            f = matches[mid]['teamsData'][str(source_id)]['formation']
            teams.append({'team_id':team_id, 'starters':[p['playerId'] for p in f['lineup']],
                          'substitutions':[{k:s[k] for k in ('playerIn','playerOut','minute')} for s in f['substitutions']]})
        data = {'match_id':mid, 'source':'https://doi.org/10.6084/m9.figshare.7770422',
                'players_source':'https://doi.org/10.6084/m9.figshare.7765196',
                'license':'CC BY 4.0', 'timing_precision':'minute',
                'source_matches_sha256':hashlib.sha256(matches_path.read_bytes()).hexdigest(),
                'source_players_sha256':hashlib.sha256(players_path.read_bytes()).hexdigest(),
                'roles':{pid:roles[int(pid)] for pid in aliases}, 'teams':teams}
        raw=(json.dumps(data,indent=2)+'\n').encode()
        (folder/'lineups.json').write_bytes(raw)
        path=folder/'manifest.json';manifest=json.loads(path.read_text())
        manifest['lineup_sha256']=hashlib.sha256(raw).hexdigest()
        path.write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--matches',type=Path,required=True);p.add_argument('--players',type=Path,required=True);p.add_argument('--root',type=Path,default=Path('fixtures/gi'))
    a=p.parse_args();prepare(a.matches,a.players,a.root)
