<script lang="ts">
  import { onMount } from 'svelte';
  import { alignLayouts, type Layout, type Version } from './parallel';
  type View = {path:string; title:string} | null;
  let {source,working,active,workingName,onactivate,onframe,theme,size} = $props<{
    source:View;working:View;active:Version;workingName:string;
    onactivate:(version:Version)=>void;onframe:(version:Version,frame:HTMLIFrameElement)=>void;
    theme:string;size:string|number;
  }>();
  let sourceFrame = $state<HTMLIFrameElement>(), workingFrame = $state<HTMLIFrameElement>();
  let unmatched = $state(0), positional = $state(false), aligned = $state(false);
  const layouts:Partial<Record<Version,Layout>>={};
  let signature='';
  const paths:Partial<Record<Version,string>>={};
  export function getFrame(version:Version) {return version==='source'?sourceFrame:workingFrame;}
  export function identify(event:MessageEvent):Version|null {
    if(!event.data?.grim)return null;
    for(const version of ['source','working'] as const) {
      const view=version==='source'?source:working;
      if(view && event.source===getFrame(version)?.contentWindow && event.data.path===new URL(view.path,location.href).pathname)return version;
    }
    return null;
  }
  const send=(version:Version,payload:object)=>getFrame(version)?.contentWindow?.postMessage({grim:true,...payload},'*');
  function align() {
    if(!layouts.source || !layouts.working)return;
    const plan=alignLayouts(layouts.source,layouts.working);
    unmatched=plan.unmatched;positional=plan.positional;aligned=true;
    const next=JSON.stringify([plan.source,plan.working]);
    if(next===signature)return;
    signature=next;
    send('source',{type:'parallel-align',...plan.source});send('working',{type:'parallel-align',...plan.working});
    send(active,{type:'parallel-sync'});
  }
  $effect(()=>{
    for(const version of ['source','working'] as const) {
      const path=(version==='source'?source:working)?.path||'';
      if(paths[version]===path)continue;
      paths[version]=path;delete layouts[version];signature='';unmatched=0;positional=false;aligned=false;
    }
  });
  $effect(()=>{
    for(const version of ['source','working'] as const){send(version,{type:'theme',theme});send(version,{type:'reading-style',size});}
  });
  onMount(()=>{
    const listener=(event:MessageEvent)=>{
      const version=identify(event);if(!version)return;
      const data=event.data;
      if(data.type==='ready') {
        delete layouts[version];signature='';
        send(version,{type:'theme',theme});send(version,{type:'reading-style',size});
        send(version,{type:'parallel-start'});
        onframe(version,getFrame(version)!);
      }else if(data.type==='parallel-layout') {
        if(!Array.isArray(data.blocks) || data.blocks.length>10000 || !Number.isFinite(data.extent) ||
          !data.blocks.every((block:Layout['blocks'][number])=>typeof block.id==='string' && typeof block.tag==='string' && Number.isFinite(block.top)))return;
        layouts[version]={blocks:data.blocks,extent:data.extent};align();
      }else if(data.type==='parallel-scroll' && version===active && Number.isFinite(data.y)) {
        send(version==='source'?'working':'source',{type:'parallel-scroll',y:data.y});
      }
    };
    window.addEventListener('message',listener);
    return ()=>window.removeEventListener('message',listener);
  });
</script>

<div class="parallel-reader" aria-label="Оригинал и рабочая копия рядом">
  {#each ['source','working'] as versions}
    {@const version=versions as Version}
    {@const view=version==='source'?source:working}
    <section class:active={active===version} aria-label={version==='source'?'Оригинал':workingName}>
      <button class="pane-label" aria-pressed={active===version} onclick={()=>onactivate(version)}>{version==='source'?'Оригинал':workingName}<span>{active===version?'Выбрано':''}</span></button>
      {#if view}
        {#if version==='source'}
          {#key view.path}<iframe bind:this={sourceFrame} title={`Оригинал: ${view.title}`} sandbox="allow-scripts allow-downloads" allow="fullscreen *" src={view.path}></iframe>{/key}
        {:else}
          {#key view.path}<iframe bind:this={workingFrame} title={`${workingName}: ${view.title}`} sandbox="allow-scripts allow-downloads" allow="fullscreen *" src={view.path}></iframe>{/key}
        {/if}
      {:else}<p class="missing-page">Соответствующей страницы в этой версии нет.</p>{/if}
    </section>
  {/each}
</div>
{#if source && working}<div class="alignment-status" role="status">{!aligned?'Выравниваем абзацы…':unmatched?'Часть абзацев без соответствия — выровнены только сопоставленные фрагменты.':positional?'Абзацы выровнены по порядку.':'Абзацы выровнены по идентификаторам.'}</div>{/if}

<style>
  .parallel-reader { flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); }
  section { display:flex; flex-direction:column; min-width:0; min-height:0; }
  section+section { border-left:1px solid var(--border,#dde2d8); }
  .pane-label { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:42px; padding:8px 20px; background:var(--panel,#f7f7f2); color:var(--muted,#667267); border:0; border-bottom:2px solid transparent; text-align:left; font-size:12px; }
  .pane-label span { font-size:10px; }
  .active .pane-label { border-bottom-color:var(--primary,#224c3c); color:var(--text,#263c34); }
  iframe { flex:1; width:100%; min-height:0; border:0; }
  .missing-page { padding:24px; color:var(--muted,#667267); font:16px/1.6 Georgia,serif; }
  .alignment-status { padding:5px 20px; color:var(--muted,#667267); font-size:10px; border-top:1px solid var(--border,#dde2d8); }
</style>
