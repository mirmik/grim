// Exercise the actual installed chapter in a separate browser context.
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';

const root=path.dirname(fileURLToPath(import.meta.url));
const registry=JSON.parse(await readFile(path.join(process.env.GRIM_LIBRARY||path.join(os.homedir(),'.grim'),'library.json'),'utf8'));
const book=registry.books.find(b=>b.title==='Дифференциальная геометрия');
const timeline=JSON.parse(await readFile(path.join(root,'output/timeline.json'),'utf8'));
const sceneTime=id=>timeline.find(s=>s.id===id).start;
const origin=process.env.GRIM_TEST_ORIGIN||'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1050}});
const page=await context.newPage();const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
try {
  await page.goto(`${origin}/?book=${book.id}`);
  await page.getByRole('button',{name:'Векторные поля и проблема сравнения',exact:false}).click();
  const frame=page.frameLocator('iframe');const video=frame.locator('video');
  await video.waitFor({state:'attached'});
  await video.evaluate(v=>new Promise((resolve,reject)=>{
    if(v.readyState>=1)return resolve();
    v.addEventListener('loadedmetadata',()=>resolve(),{once:true});
    v.addEventListener('error',()=>reject(new Error(v.error?.message)),{once:true});
  }));
  const initial=await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,paused:v.paused,
    autoplay:v.autoplay,controls:v.controls,inline:v.playsInline,fullscreen:document.fullscreenEnabled,origin:window.origin}));
  assert(Math.abs(initial.duration-timeline.at(-1).end)<.1);assert.equal(initial.width,1920);assert.equal(initial.height,1080);
  assert(initial.paused&&!initial.autoplay&&initial.controls&&initial.inline&&initial.fullscreen);
  assert.equal(initial.origin,'null');
  await frame.getByRole('button',{name:/Смотреть с .*Развёртка цилиндра/}).click();
  await video.evaluate((v,target)=>new Promise(resolve=>{
    const check=()=>{if(v.currentTime>target&&!v.paused&&!v.seeking)resolve();else setTimeout(check,100);};check();
  }),sceneTime('cylinder'));
  const playback=await video.evaluate(v=>({time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames,error:v.error?.message||null}));
  assert(playback.frames>0&&!playback.error);
  await video.evaluate(v=>{v.pause();v.textTracks[0].mode='showing';});
  await video.evaluate(v=>new Promise((resolve,reject)=>{
    let attempts=0;const check=()=>{if(v.textTracks[0].cues?.length)resolve();else if(++attempts>80)reject(new Error('Subtitles did not load'));else setTimeout(check,100);};check();
  }));
  await video.evaluate((v,t)=>new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=t;}),sceneTime('cylinder')+.8);
  const captions=await video.evaluate(v=>({count:v.textTracks[0].cues.length,active:v.textTracks[0].activeCues?.length||0}));
  assert.equal(captions.count,timeline.reduce((n,s)=>n+s.cues.length,0));assert(captions.active>0);
  await video.evaluate(v=>v.requestFullscreen());
  assert(await video.evaluate(v=>document.fullscreenElement===v));
  await video.evaluate(()=>document.exitFullscreen());
  await frame.getByRole('button',{name:/Смотреть с .*Касательная часть/}).click();
  await video.evaluate((v,target)=>new Promise(resolve=>{const check=()=>{if(v.currentTime>=target&&!v.seeking)resolve();else setTimeout(check,100);};check();}),sceneTime('projection'));
  await video.evaluate(v=>{v.pause();v.textTracks[0].mode='disabled';});
  await video.evaluate((v,t)=>new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=t;}),sceneTime('projection')+15);
  await video.evaluate(v=>v.closest('figure').scrollIntoView({block:'start'}));
  await page.screenshot({path:path.join(root,'output/player-desktop.png')});
  const range=await context.request.get(`${origin}/book/${book.id}/assets/video/vector-fields-and-comparison.mp4`,{headers:{Range:'bytes=100000-101023'}});
  assert.equal(range.status(),206);assert.equal((await range.body()).length,1024);
  assert.match(range.headers()['content-range'],/^bytes 100000-101023\//);
  assert.match(range.headers()['content-type'],/^video\/mp4/);
  await video.evaluate(v=>{v.currentTime=v.duration-.5;return v.play();});
  await video.evaluate(v=>new Promise(resolve=>{if(v.ended)resolve();else v.addEventListener('ended',resolve,{once:true});}));
  const downloadPromise=page.waitForEvent('download');
  await frame.getByRole('link',{name:'Скачать видео',exact:true}).click();
  const download=await downloadPromise;assert.equal(download.suggestedFilename(),'vector-fields-and-comparison.mp4');
  assert.equal(await download.failure(),null);
  await page.setViewportSize({width:390,height:844});
  await video.evaluate(v=>{v.currentTime=0;v.closest('figure').scrollIntoView({block:'start'});});
  const mobile=await video.evaluate(v=>({videoWidth:v.getBoundingClientRect().width,viewport:innerWidth,
    overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth}));
  assert(mobile.videoWidth>250&&mobile.videoWidth<=mobile.viewport&&!mobile.overflow);
  await page.screenshot({path:path.join(root,'output/player-mobile.png')});
  assert.deepEqual(errors,[]);
  const report={status:'passed',initial,playback,captions,fullscreen:'passed',seek_and_end:'passed',
    range_status:range.status(),download:download.suggestedFilename(),mobile,console_errors:errors};
  await writeFile(path.join(root,'output/player-check.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
} finally {await browser.close();}
