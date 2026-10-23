"""Start the local preview; optional Azure settings never leave the server."""
import argparse,ast,json,os
from pathlib import Path


def local_model_settings(path):
    allowed={'AZURE_OPENAI_ENDPOINT','AZURE_OPENAI_DEPLOYMENT','AZURE_OPENAI_API_KEY'}
    for line in path.read_text().splitlines():
        key,separator,value=line.strip().removeprefix('export ').partition('=')
        if not separator or key not in allowed:continue
        value=value.strip()
        if value.startswith(('"',"'")):
            try:value=ast.literal_eval(value)
            except (ValueError,SyntaxError):raise SystemExit('Invalid quoting in local model settings.') from None
        if isinstance(value,str):os.environ.setdefault(key,value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--azure',action='store_true',help='Enable bounded intent and narrative selection using existing local model credentials')
    workflow=parser.add_mutually_exclusive_group()
    workflow.add_argument('--agent',action='store_true',help='Use bounded Agent Framework research; requires --azure')
    workflow.add_argument('--multiagent',action='store_true',help='Use Footie with Match and Career specialists; requires --azure')
    parser.add_argument('--port',type=int,default=8017)
    parser.add_argument('--commentary-dir',type=Path,help='Serve already validated local commentary bundles without cloud synthesis')
    parser.add_argument('--voice',choices=['broadcast','british','natural'],default='broadcast')
    args=parser.parse_args()
    if (args.agent or args.multiagent) and not args.azure:parser.error('Agent workflows require --azure')
    if args.multiagent:os.environ['COUNTERPRESS_ASSISTANT_WORKFLOW']='multiagent'
    elif args.agent:os.environ['COUNTERPRESS_ASSISTANT_WORKFLOW']='agent'
    else:os.environ.pop('COUNTERPRESS_ASSISTANT_WORKFLOW',None)
    if args.commentary_dir:
        from counterpress.api.snapshots import SCENARIOS
        from counterpress.fixture import load_fixture
        from counterpress.live.highlight_narrative import SCRIPTS,narrative,validate_asset
        try:
            for language in ('en','zh-Hans'):
                for story in SCRIPTS:
                    script=narrative(load_fixture(Path('fixtures')/SCENARIOS[story][0]).events,language,args.voice)
                    validate_asset(json.loads((args.commentary_dir/(script['key']+'.json')).read_text()),script)
        except (OSError,ValueError,KeyError):
            raise SystemExit('Prepare and validate every commentary bundle before enabling the local voice preview.') from None
        os.environ['COUNTERPRESS_COMMENTARY_DIR']=str(args.commentary_dir.resolve())
        os.environ['COUNTERPRESS_COMMENTARY_VOICE']=args.voice
        os.environ['COUNTERPRESS_SPEECH']='azure'
    if args.azure:
        local_model_settings(Path('.env'))
        from counterpress.adaptation.azure import load_config
        try:config=load_config()
        except ValueError:raise SystemExit('Local Azure configuration is incomplete or invalid.') from None
        if not config:raise SystemExit('Local Azure configuration is missing.')
        os.environ['COUNTERPRESS_ASSISTANT_MODEL']='azure'
    else:os.environ.pop('COUNTERPRESS_ASSISTANT_MODEL',None)
    os.environ['COUNTERPRESS_STREAMING']='off'
    os.environ['COUNTERPRESS_STORAGE']='sqlite'
    os.environ['COUNTERPRESS_DB_PATH']='var/footie-local.sqlite3'
    os.environ['COUNTERPRESS_PROFILE_DB_PATH']=':memory:'
    os.environ['COUNTERPRESS_STATIC_DIR']='frontend/dist'
    import uvicorn
    uvicorn.run('counterpress.api.main:app',host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
