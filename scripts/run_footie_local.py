"""Start the local preview; optional Azure settings never leave the server."""
import argparse,ast,os
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
    parser.add_argument('--port',type=int,default=8017)
    args=parser.parse_args()
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
