"""Build reviewed whole-highlight audio with Azure's own bookmark timings.

Requires local azure-cognitiveservices-speech==1.52.0 (authoring only, not runtime).
Uses existing Speech F0 identity/cache/quota. Outputs under ignored var/ by default.
--publish uploads validated bundles to the existing PRIVATE speech-cache container.
"""
import argparse, base64, json, os, time
from pathlib import Path
from counterpress.api.snapshots import SCENARIOS
from counterpress.fixture import load_fixture
from counterpress.live.speech import AzureSpeech
from counterpress.live.highlight_narrative import narrative, validate_asset, SCRIPTS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');parser.add_argument('--story',choices=list(SCRIPTS));parser.add_argument('--language',choices=['en','zh-Hans']);parser.add_argument('--voice',choices=['broadcast','british','natural'],default='broadcast');args=parser.parse_args()
    import azure.cognitiveservices.speech as sdk
    service=AzureSpeech();directory=Path('var/commentary');directory.mkdir(parents=True,exist_ok=True)
    for language in ([args.language] if args.language else ['en','zh-Hans']):
        for story in ([args.story] if args.story else SCRIPTS):
            events=load_fixture(Path('fixtures')/SCENARIOS[story][0]).events
            script=narrative(events,language,args.voice);target=directory/(script['key']+'.json')
            if target.exists():asset=validate_asset(json.loads(target.read_text()),script)
            else:
                text=' '.join(b['text'] for b in script['beats'])
                service.reserve(sum(2 if ord(c)>127 else 1 for c in text))
                config=sdk.SpeechConfig(endpoint=service.endpoint,token_credential=service.credential)
                config.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
                synthesizer=sdk.SpeechSynthesizer(speech_config=config,audio_config=None)
                marks={}
                synthesizer.bookmark_reached.connect(lambda e:marks.__setitem__(e.text,e.audio_offset/10_000_000))
                result=synthesizer.speak_ssml_async(script['ssml']).get()
                if result.reason!=sdk.ResultReason.SynthesizingAudioCompleted:raise RuntimeError('Azure narration failed; private provider details withheld')
                if len(marks)!=len(script['beats']):raise RuntimeError('Azure did not return every timing marker')
                asset={'key':script['key'],'source_hash':script['source_hash'],'duration':result.audio_duration.total_seconds(),
                       'markers':[{'at':marks[f'b{i}'],**b} for i,b in enumerate(script['beats'])],
                       'audio':base64.b64encode(result.audio_data).decode()}
                validate_asset(asset,script);target.write_text(json.dumps(asset,ensure_ascii=False))
                # Authoring is serial; also spaces new F0 syntheses across minute boundaries.
                time.sleep(5)
            (directory/(f'{story}-{language}'+('' if args.voice=='broadcast' else '-'+args.voice)+'.mp3')).write_bytes(base64.b64decode(asset['audio']))
            if args.publish:service.cache.get_blob_client('narration/v2/'+script['key']+'.json').upload_blob(json.dumps(asset,ensure_ascii=False).encode(),overwrite=True)
            print(f'{story} {language}: {asset["duration"]:.2f}s, {len(asset["markers"])} phrase markers, {"published" if args.publish else "local preview"}',flush=True)

if __name__=='__main__':main()
