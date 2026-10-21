// Deterministic derivatives only: preserve approved artwork, framing and identity.
// Requires sharp 0.35.5 (authoring tool; not needed in production).
const sharp=require('sharp'),fs=require('node:fs/promises'),path=require('node:path');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'frontend/src/football/portraits');
(async()=>{
  const files=(await fs.readdir(dir)).filter(f=>f.endsWith('-portrait-v1.jpg')).sort();
  if(files.length!==44)throw Error('Expected the 44 approved player portraits');
  const rows=[];
  for(const file of files){
    for(const width of [256,384,768]){
      const name=file.replace('.jpg',`-${width}.webp`);
      const result=await sharp(path.join(dir,file)).resize({width,withoutEnlargement:true}).webp({quality:width===768?88:84,effort:6}).toFile(path.join(dir,name));
      rows.push({file:name,width:result.width,bytes:result.size});
    }
  }
  await sharp(path.join(root,'frontend/src/assets/brand/footie-wordmark-forest-v1.png')).resize({width:652}).webp({quality:92,alphaQuality:100,effort:6}).toFile(path.join(root,'frontend/src/assets/brand/footie-wordmark-forest-v1.webp'));
  console.log(JSON.stringify({portraits:files.length,derivatives:rows.length,totalBytes:rows.reduce((s,r)=>s+r.bytes,0),pitchBytes:rows.filter(r=>r.width===256).reduce((s,r)=>s+r.bytes,0)},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
