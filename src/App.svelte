<script lang="ts">
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import Library from './Library.svelte';
  import AgentPanel from './AgentPanel.svelte';
  import ThemePicker from './ThemePicker.svelte';
  import { resolvedTheme } from './theme';
  import { readingSize, readingSizes, setReadingSize, type ReadingSize } from './reading';
  import NotesPanel from './NotesPanel.svelte';
  import ParallelReader from './ParallelReader.svelte';
  import { loadLocalNotes, loadNotes, noteAnchor, saveLocalNotes, saveNotes, type NoteAnchor, type ReaderNote } from './notes';
  import { appPath, offline, fetchBook } from './platform';
  type Page = {id:string; title:string; path?:string; children?:Page[]};
  type Position = {visible_text:string; selection:string; anchor:string; scroll_y:number; anchor_offset:number;block_index?:number};
  type Version = 'working'|'source';
  let mainView = true;
  let renamingCopy = $state(false), copyName = $state(''), savingCopyName = $state(false);
  let version = $state<Version>('working'), creatingCopy = $state(false);
  type Book = {working_name?:string;working_directory?:string;content_prefix?:string;has_source?:boolean;working_root?:string;id:string;title:string;subtitle?:string;pages:Page[];root:string;bridge_version?:string};
  let book = $state<Book|null>(null), bookId = $state<string|null>(null);
  let current = $state<Page|null>(null), revision = $state(0), connected = $state(false), error = $state('');
  let frame = $state<HTMLIFrameElement>();
  let comparison = $state<ParallelReader>();
  let readingWidth = $state(0), parallelEnabled = $state(true), copyRevision = $state(0);
  let sourceBook = $state<Book|null>(null), workingBook = $state<Book|null>(null);
  let parallel = $derived(!offline && !!book?.has_source && parallelEnabled && readingWidth>=960);
  const panePositions:Partial<Record<Version,Position>>={};
  let paneNotes:Record<Version,ReaderNote[]>={source:[],working:[]};
  function pairedPage(next:Version):Page|null {
    const other=next==='source'?sourceBook:workingBook;
    if(!other || !current)return null;
    const pages=flatten(other.pages);
    return pages.find(page=>page.id===current!.id)||pages.find(page=>page.path===current!.path)||null;
  }
  function comparisonView(next:Version) {
    const data=next==='source'?sourceBook:workingBook, page=pairedPage(next);
    return data && page?.path ? {title:page.title,path:framePath(page.path,data,next==='working'?copyRevision:revision)} : null;
  }
  function activatePane(next:Version) {
    if(!parallel || next===version)return;
    const data=next==='source'?sourceBook:workingBook,page=pairedPage(next);
    if(!data || !page)return;
    savePosition();panePositions[version]={...position};paneNotes[version]=notes;
    book=data;current=page;version=next;mainView=next==='source';
    position={...(panePositions[next]||empty())};notes=paneNotes[next];
    frame=comparison?.getFrame(next);noteSelection='';selectionAnchor=null;noteAction=null;returnLocations=[];noteStatus={};
    history.replaceState({},'',`?book=${encodeURIComponent(book.id)}${next==='working'?'&version=working':''}`);
    syncNotes();savePosition();void publish();
  }
  function comparisonReady(next:Version,element:HTMLIFrameElement) {
    if(next===version)frame=element;
    const page=pairedPage(next);
    const restored=next===version ? (pendingHash?{...empty(),anchor:pendingHash,anchor_offset:24}:$state.snapshot(position)) : panePositions[next]||empty();
    element.contentWindow?.postMessage({grim:true,type:'restore',position:restored},'*');
    if(next===version){pendingHash='';syncNotes(pendingNoteId);pendingNoteId='';}
    else element.contentWindow?.postMessage({grim:true,type:'notes',notes:$state.snapshot(paneNotes[next].filter(note=>note.page_id===page?.id).map(note=>({id:note.id,anchor:note.anchor})))},'*');
  }
  function toggleParallel() {
    savePosition();panePositions[version]={...position};parallelEnabled=!parallelEnabled;
    try{localStorage.setItem('grim-parallel',String(parallelEnabled));}catch{}
  }
  let headerHeight = $state(65);
  let showTools = $state(false);
  let toc = $state<HTMLElement>();
  let toolsButton = $state<HTMLButtonElement>();
  function closeOverlays() { sidebar=false;showTools=false; }
  function toggleToc() {
    sidebar=!sidebar;showTools=false;showAgent=false;showContext=false;showNotes=false;
    if(sidebar) requestAnimationFrame(()=>toc?.querySelector<HTMLElement>('.page-link.active')?.focus());
  }
  function togglePanel(panel: 'notes'|'context'|'agent') {
    const wasOpen = panel==='notes'?showNotes:panel==='context'?showContext:showAgent;
    closeOverlays();showNotes=panel==='notes'&&!wasOpen;showContext=panel==='context'&&!wasOpen;showAgent=panel==='agent'&&!wasOpen;
  }
  function sendReadingSize() {
    frame?.contentWindow?.postMessage({grim:true,type:'reading-style',size:$readingSize}, '*');
  }
  $effect(() => { sendReadingSize(); });
  function sendTheme() {
    frame?.contentWindow?.postMessage({grim:true,type:'theme',theme:$resolvedTheme}, '*');
  }
  $effect(() => { sendTheme(); });
  let token = $state('');
  let notesWrite:Promise<void> = Promise.resolve();
  let lastRevision = -1, pendingHash = '', generation = 0, sequence = 0;
  let events:EventSource|null = null;
  let readerId = $state('');
  const empty = ():Position => ({visible_text:'',selection:'',anchor:'',scroll_y:0,anchor_offset:0});
  let position = $state<Position>(empty());
  let returnLocations = $state<{page_id:string;position:Position}[]>([]);
  let canReturn = $derived(returnLocations.some(place=>allPages.some(page=>page.id===place.page_id)));
  let pageCharacters = $state<number|null>(null), countedFrame = $state('');
  let showAgent = $state(false), showContext = $state(false), showNotes = $state(false), sidebar = $state(false), updated = $state('');
  let notes = $state<ReaderNote[]>([]), noteSelection = $state(''), selectionAnchor = $state<NoteAnchor|null>(null), noteAction = $state<{x:number;y:number}|null>(null), noteStatus = $state<Record<string,string>>({});
  let pendingNoteId = '';
  let contextStatus = $state('Ожидание страницы');
  const flatten = (nodes:Page[]):Page[] => nodes.flatMap(n => [...(n.path ? [n] : []), ...flatten(n.children || [])]);
  let allPages = $derived(book ? flatten(book.pages) : []);
  let pageIndex = $derived(allPages.findIndex(p=>p.id===current?.id));
  let prefix = $derived(book?.content_prefix || `/book/${bookId}/`);
  const encodedPath = (path:string) => path.split('/').map(encodeURIComponent).join('/');
  function framePath(path:string,view:Book|null=book,viewRevision=parallel && view===workingBook?copyRevision:revision) {
    const encoded=encodedPath(path);
    const base=view?.content_prefix || `/book/${bookId}/`;
    if(offline || !view?.bridge_version)return base+encoded;
    const parts=encoded.split('/'),name=parts.pop()!;
    parts.push(`__grim_v_${encodeURIComponent(view.bridge_version)}_${viewRevision}__${name}`);
    return base+parts.join('/');
  }
  function currentNotes() {return notes.filter(note=>note.page_id===current?.id);}
  function syncNotes(focus='') {
    // The sandbox receives only anchors needed for rendering, never the user's note text.
    const rendered=currentNotes().map(note=>({id:note.id,anchor:$state.snapshot(note.anchor)}));
    frame?.contentWindow?.postMessage({grim:true,type:'notes',notes:rendered},'*');
    const note=focus&&notes.find(item=>item.id===focus);
    if(note)requestAnimationFrame(()=>frame?.contentWindow?.postMessage({grim:true,type:'focus-note',note:{id:note.id,anchor:$state.snapshot(note.anchor)}},'*'));
  }
  function persistNotes(next:ReaderNote[]) {
    if(!book)return;
    const id=book.id,writeToken=token,writeVersion=version;
    notes=next;const saved=$state.snapshot(next);syncNotes();
    paneNotes[version]=saved;
    if(offline){saveLocalNotes(id,saved);return;}
    notesWrite=notesWrite.catch(()=>{}).then(()=>saveNotes(id,writeToken,saved,writeVersion)).catch(cause=>{error=String(cause);});
  }
  function createNote(text:string) {
    if(!current || !selectionAnchor || !noteSelection.trim())return;
    const now=new Date().toISOString();
    const note:ReaderNote={id:crypto.randomUUID(),page_id:current.id,page_title:current.title,text,anchor:$state.snapshot(selectionAnchor),created_at:now,updated_at:now};
    persistNotes([note,...notes]);noteStatus={...noteStatus,[note.id]:'exact'};
    noteSelection='';selectionAnchor=null;noteAction=null;
    frame?.contentWindow?.postMessage({grim:true,type:'clear-selection'},'*');
  }
  function updateNote(id:string,text:string) {
    persistNotes(notes.map(note=>note.id===id?{...note,text,updated_at:new Date().toISOString()}:note));
  }
  function deleteNote(id:string) {persistNotes(notes.filter(note=>note.id!==id));}
  function openNote(note:ReaderNote) {
    const page=allPages.find(item=>item.id===note.page_id);
    if(!page){noteStatus={...noteStatus,[note.id]:'missing'};return;}
    showNotes=true;showAgent=false;showContext=false;
    if(current?.id!==page.id){pendingNoteId=note.id;select(page);}else syncNotes(note.id);
  }
  const readingKey=(id:string,v:Version=version)=>`grim-reading:${id}${v==='source'?':source':''}`;
  function savePosition() {
    if (!book || !current) return;
    try {localStorage.setItem(readingKey(book.id),JSON.stringify({page_id:current.id,position:{...position,selection:'',visible_text:''}}));}catch{}
  }
  function savedPosition(id:string,v:Version=version):{page_id?:string;position?:Position} {
    try {
      const saved=JSON.parse(localStorage.getItem(readingKey(id,v))||'{}');
      const p=saved.position;
      if (!p || typeof saved.page_id!=='string' || typeof p.anchor!=='string' || ![p.scroll_y,p.anchor_offset].every(Number.isFinite)) return {};
      return {page_id:saved.page_id,position:{...empty(),anchor:p.anchor,scroll_y:Math.max(0,p.scroll_y),anchor_offset:p.anchor_offset,...(Number.isSafeInteger(p.block_index)&&p.block_index>=0?{block_index:p.block_index}:{})}};
    }catch{return {};}
  }
  async function publish() {
    if (!book || (!current && allPages.length)) return;
    if (offline) {contextStatus='Чтение на устройстве';return;}
    const epoch=generation;
    const payload={reader_id:readerId,sequence:++sequence,book_id:book.id,version,page_id:current?.id||null,...position};
    try {
      const response = await fetch('/api/viewer/context', {method:'POST',headers:{'Content-Type':'application/json','X-Grim-Viewer':token},body:JSON.stringify(payload)});
      if (!response.ok) throw new Error('Контекст недоступен');
      if(epoch===generation)contextStatus='Контекст доступен агенту';
    }catch{if(epoch===generation)contextStatus='Не удалось передать контекст';}
  }
  function idle() {
    if (offline || !token) return;
    void fetch('/api/viewer/idle',{method:'POST',headers:{'Content-Type':'application/json','X-Grim-Viewer':token},body:JSON.stringify({reader_id:readerId,sequence:++sequence})}).catch(()=>{});
  }
  function select(page:Page,hash='',restored:Position|null=null) {
    const samePage=current?.path===page.path;
    current=page;position=restored?{...restored}:empty();noteSelection='';selectionAnchor=null;noteAction=null;pendingHash=hash;closeOverlays();contextStatus='Ожидание страницы';
    if(!samePage){panePositions.source=empty();panePositions.working=empty();}
    if(samePage) {
      frame?.contentWindow?.postMessage({grim:true,type:'restore',position:hash?{...empty(),anchor:hash,anchor_offset:24}:$state.snapshot(position)},'*');
      pendingHash='';
    }
    savePosition();void publish();
  }
  function rememberLocation() {
    if(!current)return;
    returnLocations=[...returnLocations.slice(-49),{page_id:current.id,position:{...position,selection:'',visible_text:''}}];
  }
  function returnToReading() {
    while(returnLocations.length) {
      const place=returnLocations[returnLocations.length-1];
      returnLocations=returnLocations.slice(0,-1);
      const page=allPages.find(item=>item.id===place.page_id);
      if(page){select(page,'',place.position);return;}
    }
  }
  async function loadBook(id:string,epoch:number) {
    const response=await fetchBook(id,mainView?'main':version);
    if(!response.ok) throw new Error((await response.json()).detail||'Не удалось открыть книгу');
    const data=await response.json();
    if(epoch!==generation)return null;
    const loadedVersion:Version=data.version||'working', writerToken=data.writer_token;
    const loadedNotes=offline ? loadLocalNotes(id) : await loadNotes(id,writerToken,loadedVersion);
    if(epoch!==generation)return null;
    let other:Book|null=null, otherNotes:ReaderNote[]=[];
    const otherVersion=loadedVersion==='source'?'working':'source';
    if(data.has_source && !offline) {
      const [response,loadedOtherNotes]=await Promise.all([fetchBook(id,otherVersion),loadNotes(id,writerToken,otherVersion)]);
      if(!response.ok)throw new Error((await response.json()).detail||'Не удалось открыть вторую версию');
      other=await response.json();otherNotes=loadedOtherNotes;
      if(epoch!==generation)return null;
    }
    // A reader can choose the other pane while metadata is being refreshed.
    // Commit both fetched versions together without undoing that choice.
    const activeVersion=book && parallel ? version : loadedVersion;
    if(other) {
      sourceBook=loadedVersion==='source'?data:other;workingBook=loadedVersion==='working'?data:other;
      paneNotes={...paneNotes,[loadedVersion]:loadedNotes,[otherVersion]:otherNotes};
    }else{sourceBook=null;workingBook=null;}
    version=activeVersion;token=writerToken;
    const activeData=activeVersion===loadedVersion ? data : other!;
    const pages=flatten(activeData.pages),saved=savedPosition(id);
    const next=pages.find(p=>p.id===(current?.id||saved.page_id))||pages[0]||null;
    if(!current || current.id!==next?.id) {
      position=next && next.id===saved.page_id && saved.position ? saved.position:empty();
    }
    if(other) {
      const savedOther=savedPosition(id,otherVersion);
      if(!panePositions[otherVersion] && savedOther.page_id===next?.id)panePositions[otherVersion]=savedOther.position;
    }
    book=activeData;current=next;notes=other?paneNotes[activeVersion]:loadedNotes;error='';
    if(!next)void publish();
    return data;
  }
  async function openBook(id:string,push=true,nextVersion:Version|'main'='main') {
    closeOverlays();
    savePosition();idle();events?.close();events=null;
    const epoch=++generation;
    mainView=nextVersion!=='working';
    version=offline||nextVersion==='main'?'working':nextVersion;
    returnLocations=[];renamingCopy=false;sourceBook=null;workingBook=null;delete panePositions.source;delete panePositions.working;paneNotes={source:[],working:[]};
    bookId=id;book=null;current=null;position=empty();noteSelection='';selectionAnchor=null;noteAction=null;notes=[];noteStatus={};pendingHash='';pendingNoteId='';error='';updated='';connected=false;sidebar=false;showAgent=false;showContext=false;showNotes=false;
    if(push)history.pushState({},'',`?book=${encodeURIComponent(id)}${nextVersion==='working'?'&version=working':''}`);
    try {
      const data=await loadBook(id,epoch);if(!data)return;
      revision++;copyRevision++;lastRevision=data.revision;
      if (offline) {connected=true;return;}
      const stream=new EventSource(`/api/books/${id}/events`);events=stream;
      stream.onopen=()=>{if(epoch===generation)connected=true;};
      stream.onerror=()=>{if(epoch===generation){connected=false;lastRevision=-1;}};
      stream.onmessage=async event=>{
        const message=JSON.parse(event.data);
        if(epoch!==generation || message.book_id!==id || message.revision===lastRevision)return;
        lastRevision=message.revision;
        // Working edits must not reload an unchanged original (or interrupt its media).
        const onlyWorking=book?.working_directory && Array.isArray(message.changed) && message.changed.every((path:string)=>path.startsWith(book!.working_directory+'/'));
        try {
          if(await loadBook(id,epoch)) {
            if(!onlyWorking || (!parallel && version==='working'))revision++;copyRevision++;updated=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
          }
        }catch(e){if(epoch===generation)error=String(e);}
      };
    }catch(e){if(epoch===generation)error=String(e);}
  }
  async function createWorkingCopy() {
    if(!bookId || creatingCopy)return;
    const id=bookId,epoch=generation;
    creatingCopy=true;error='';
    try {
      await notesWrite;
      if(epoch!==generation)return;
      const response=await fetch(`/api/books/${id}/working-copy`,{method:'POST',headers:{'X-Grim-Viewer':token}});
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail||'Не удалось создать рабочую копию');
      if(epoch===generation) {
        // The current reading place belongs to the main document.
        try {localStorage.setItem(`grim-reading:${id}:source`,JSON.stringify({page_id:current?.id,position:{...position,selection:'',visible_text:''}}));}catch{}
        await openBook(id,false,'main');
        history.replaceState({},'',`?book=${encodeURIComponent(id)}`);
      }
    }catch(e){if(epoch===generation)error=String(e);}finally{creatingCopy=false;}
  }
  async function renameCopy(event:SubmitEvent) {
    event.preventDefault();
    if(!bookId || !copyName.trim() || savingCopyName)return;
    const id=bookId,epoch=generation;
    savingCopyName=true;error='';
    try {
      await notesWrite;
      const response=await fetch(`/api/books/${id}/working-copy`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Grim-Viewer':token},body:JSON.stringify({title:copyName.trim()})});
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail||'Не удалось переименовать копию');
      if(epoch===generation){await loadBook(id,epoch);renamingCopy=false;}
    }catch(e){if(epoch===generation)error=String(e);}finally{savingCopyName=false;}
  }
  async function switchVersion(next:Version) {
    if(!bookId || version===next)return;
    if(parallel){activatePane(next);return;}
    const id=bookId,epoch=generation;
    await notesWrite;
    if(epoch===generation)await openBook(id,true,next);
  }
  function showLibrary(push=true) {
    closeOverlays();
    returnLocations=[];
    savePosition();idle();generation++;events?.close();events=null;bookId=null;book=null;current=null;notes=[];noteSelection='';selectionAnchor=null;noteAction=null;showAgent=false;showContext=false;showNotes=false;error='';
    if(push)history.pushState({},'',appPath);
  }
  onMount(()=>{
    readerId=crypto.randomUUID();
    try{parallelEnabled=localStorage.getItem('grim-parallel')!=='false';}catch{}
    const navigate=()=>{
      const id=new URLSearchParams(location.search).get('book');
      const v=new URLSearchParams(location.search).get('version')==='working'?'working':'main';
      if(id)void openBook(id,false,v);else showLibrary(false);
    };
    const listener=(event:MessageEvent)=>{
      const data=event.data;
      if(parallel) {
        const incoming=comparison?.identify(event);if(!incoming)return;
        if(data.type==='activate'){activatePane(incoming);return;}
        if(data.type==='ready')return;
        if(incoming!==version) {
          if(data.type==='context' && typeof data.anchor==='string' && [data.scroll_y,data.anchor_offset].every(Number.isFinite))panePositions[incoming]={...empty(),anchor:data.anchor,scroll_y:Math.max(0,data.scroll_y),anchor_offset:data.anchor_offset,...(Number.isSafeInteger(data.block_index)&&data.block_index>=0?{block_index:data.block_index}:{})};
          return;
        }
        frame=comparison?.getFrame(version);
      }else if(event.source!==frame?.contentWindow || !data?.grim || !current?.path || data.path!==framePath(current.path))return;
      if(!current?.path)return;
      if(data.type==='ready') {
        sendTheme();
        sendReadingSize();
        frame?.contentWindow?.postMessage({grim:true,type:'restore',position:pendingHash?{...empty(),anchor:pendingHash,anchor_offset:24}:$state.snapshot(position)},'*');pendingHash='';
        syncNotes(pendingNoteId);pendingNoteId='';
      }else if(data.type==='context') {
        if(![data.visible_text,data.selection,data.anchor].every(x=>typeof x==='string') || ![data.scroll_y,data.anchor_offset].every(Number.isFinite))return;
        position={visible_text:data.visible_text.slice(0,24000),selection:data.selection.slice(0,12000),anchor:data.anchor.slice(0,300),scroll_y:Math.max(0,data.scroll_y),anchor_offset:data.anchor_offset,...(Number.isSafeInteger(data.block_index)&&data.block_index>=0?{block_index:data.block_index}:{})};
        panePositions[version]={...position};
        if(Number.isSafeInteger(data.page_characters) && data.page_characters>=0) {
          pageCharacters=data.page_characters;countedFrame=data.path;
        }
        const exact=position.selection.replace(/\s+/g,' ').trim();
        const nextAnchor=noteAnchor(data.selection_anchor) || (exact ? {exact,prefix:'',suffix:'',element_id:'',block_text:exact,start:0,end:exact.length} : null);
        // Keep the latest real selection for note creation: focusing a parent
        // control may collapse the iframe selection before the user can save it.
        if(position.selection.trim() && nextAnchor){
          noteSelection=position.selection;selectionAnchor=nextAnchor;
          const rect=data.selection_rect,frameRect=frame?.getBoundingClientRect();
          if(frameRect && rect && [rect.left,rect.top,rect.bottom,rect.width].every(Number.isFinite)){
            const x=Math.max(85,Math.min(innerWidth-85,frameRect.left+rect.left+rect.width/2));
            let y=frameRect.top+rect.top-12;if(y<82)y=frameRect.top+rect.bottom+12;
            noteAction={x,y:Math.max(70,Math.min(innerHeight-70,y))};
          }else noteAction={x:innerWidth/2,y:innerHeight-80};
        }
        savePosition();void publish();
      }else if(data.type==='notes-status' && data.resolved && Array.isArray(data.missing)) {
        noteStatus={...noteStatus,...data.resolved,...Object.fromEntries(data.missing.filter((id:unknown)=>typeof id==='string').map((id:string)=>[id,'missing']))};
      }else if((data.type==='download'||data.type==='navigate') && typeof data.href==='string') {
        const url=new URL(data.href,location.origin);
        if(url.origin!==location.origin || !url.pathname.startsWith(prefix))return;
        if(data.type==='download') {
          const link=document.createElement('a');link.href=url.pathname+'?download=1';link.download='';link.click();
        }else {
          const page=url.pathname===framePath(current.path)?current:allPages.find(p=>prefix+encodedPath(p.path!)===url.pathname);
          if(page){rememberLocation();select(page,decodeURIComponent(url.hash.slice(1)));}
        }
      }
    };
    const background=()=>{if(document.visibilityState==='hidden')savePosition();};
    const back=(event:Event)=>{
      if(showTools){showTools=false;toolsButton?.focus();event.preventDefault();}
      else if(showAgent){showAgent=false;event.preventDefault();}
      else if(showContext){showContext=false;event.preventDefault();}
      else if(showNotes){showNotes=false;event.preventDefault();}
      else if(sidebar){sidebar=false;event.preventDefault();}
      else if(bookId){showLibrary();event.preventDefault();}
    };
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape' && (showTools||sidebar||showAgent||showContext||showNotes))back(event);};
    window.addEventListener('keydown',escape);
    document.addEventListener('visibilitychange',background);
    window.addEventListener('pagehide',savePosition);
    window.addEventListener('grim-back',back);
    window.addEventListener('message',listener);window.addEventListener('popstate',navigate);navigate();
    return ()=>{window.removeEventListener('keydown',escape);document.removeEventListener('visibilitychange',background);window.removeEventListener('pagehide',savePosition);window.removeEventListener('grim-back',back);generation++;events?.close();window.removeEventListener('message',listener);window.removeEventListener('popstate',navigate);};
  });
</script>

{#snippet tree(nodes:Page[], depth=0)}
  {#each nodes as page}
    {#if page.path}
      <button class:active={current?.id===page.id} class="page-link" style:padding-left={`${18+depth*14}px`} onclick={()=>select(page)}><span class="page-symbol">▤</span>{page.title}{#if current?.id===page.id}<span class="current-dot"></span>{/if}</button>
    {:else}
      <div class="chapter" style:padding-left={`${18+depth*14}px`}>{page.title}</div>
    {/if}
    {#if page.children}{@render tree(page.children,depth+(page.path ? 1 : 0))}{/if}
  {/each}
{/snippet}

{#if !bookId}
  <Library onopen={(id)=>{void openBook(id);}}/>
{:else}
<div class="app-shell" class:offline style:--reader-header-height={`${headerHeight}px`}>
  {#if sidebar || showTools}<button class="reader-backdrop" aria-label="Закрыть меню" onclick={()=>{closeOverlays();toolsButton?.focus();}}></button>{/if}
  <aside id="reader-toc" bind:this={toc} class:mobile-open={sidebar}>
    <a class="brand" href={appPath} aria-label="Grim, главная"><span class="brand-mark">g</span><span>grim<span class="brand-period">.</span></span></a>
    <button class="back-library" onclick={()=>showLibrary()}>← Библиотека</button>
    <div class="library-label">ВАША ЖИВАЯ КНИГА</div>
    <div class="book-title">{book?.title || 'Открываем книгу…'}</div>
    <p class="book-description">{book?.subtitle || 'Пространство для любопытства'}</p>
    {#if book && !offline}
      <div class="book-versions">
        {#if book.has_source}
          <button class:chosen={version==='source'} aria-pressed={version==='source'} onclick={()=>switchVersion('source')}>Оригинал</button>
          <div class="copy-controls">
            <button class="copy-version" class:chosen={version==='working'} aria-pressed={version==='working'} title={book.working_name||'Рабочая копия'} onclick={()=>switchVersion('working')}>{book.working_name||'Рабочая копия'}</button>
            <button class="rename-copy" aria-label="Переименовать рабочую копию" title="Переименовать рабочую копию" aria-expanded={renamingCopy} aria-controls="rename-copy-form" onclick={()=>{copyName=book?.working_name||'Рабочая копия';renamingCopy=!renamingCopy;}}>
              <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m16 3 5 5M4 15 16 3a2.1 2.1 0 0 1 5 5L9 20l-6 1z"/></svg>
            </button>
          </div>
          {#if readingWidth>=960}<button aria-label="Показывать оригинал и копию рядом" aria-pressed={parallelEnabled} onclick={toggleParallel}>{parallelEnabled?'Рядом ✓':'Рядом'}</button>{/if}
          {#if renamingCopy}<form id="rename-copy-form" onsubmit={renameCopy}><label>Название рабочей копии<input bind:value={copyName} maxlength="200" required /></label><button disabled={savingCopyName}>Сохранить название</button><button type="button" onclick={()=>renamingCopy=false}>Отмена</button></form>{/if}
        {:else}
          <button disabled={creatingCopy || !allPages.length} onclick={createWorkingCopy}>{creatingCopy?'Создаём копию…':'Создать рабочую копию'}</button>
        {/if}
      </div>
    {/if}
    <div class="toc-label">ОГЛАВЛЕНИЕ <span>{allPages.length.toString().padStart(2,'0')}</span></div>
    <nav aria-label="Оглавление">{#if book}{@render tree(book.pages)}{/if}</nav>
    <div class="sidebar-bottom"><div class="connection"><span class:online={connected}></span>{offline ? 'Книга на устройстве' : connected ? 'Книга обновляется с диска' : 'Восстанавливаем соединение…'}</div><p>{offline ? 'Читайте без сети. Место в книге сохраняется автоматически.' : 'Читайте. Исследуйте. Задавайте вопросы своему агенту.'}</p><span class="version">GRIM / PROTOTYPE 0.2</span></div>
  </aside>
  <main>
    <header bind:clientHeight={headerHeight}>
      <button class="menu-button" aria-label="Оглавление" aria-expanded={sidebar} aria-controls="reader-toc" onclick={toggleToc}><span aria-hidden="true">☰</span> Оглавление</button>
      <div class="breadcrumbs"><button class="breadcrumb-library" onclick={()=>showLibrary()}>Библиотека</button> <span>/</span> <strong>{current?.title || 'Grim'}</strong></div>
      <div id="reader-tools" class="reader-actions" class:tools-open={showTools}>
        <div class="font-settings">
          <label for="reading-size">Размер текста</label>
          <select id="reading-size" value={$readingSize} onchange={event=>setReadingSize(event.currentTarget.value==='auto'?'auto':Number(event.currentTarget.value) as ReadingSize)}>
            <option value="auto">По умолчанию</option>
            {#each readingSizes as size}<option value={size}>{size} px</option>{/each}
          </select>
        </div>
        <ThemePicker/>
        <button class="context-toggle" class:selected={showNotes} onclick={()=>togglePanel('notes')}>Заметки {#if notes.length}<b>{notes.length}</b>{/if}</button>
        <button class="context-toggle" aria-label={offline ? 'Фрагмент' : 'Контекст чтения'} class:selected={showContext} onclick={()=>togglePanel('context')}><span aria-hidden="true">⌘</span> <span class="context-label">{offline ? 'Фрагмент' : 'Контекст чтения'}</span> {#if position.selection}<i></i>{/if}</button>
        {#if !offline && book}<button class="context-toggle agent-toggle" class:selected={showAgent} onclick={()=>togglePanel('agent')}>Чат с агентом</button>{/if}
      </div>
      <button bind:this={toolsButton} class="tools-button" aria-label="Настройки и действия" aria-expanded={showTools} aria-controls="reader-tools" onclick={()=>{showTools=!showTools;sidebar=false;}}>Aa <span aria-hidden="true">⋮</span></button>
    </header>
    {#if error}<div class="error" role="alert">{error}</div>{/if}
    <div class="reading-area">
      <section class="page-area" aria-label="Страница книги" bind:clientWidth={readingWidth}>
        <div class="reading-meta"><span>{current ? 'ГЛАВА '+(pageIndex+1).toString().padStart(2,'0') : 'НОВАЯ КНИГА'}</span><span>{book?.has_source ? (version==='source'?'Оригинал':book.working_name||'Рабочая копия') : updated ? `Обновлено в ${updated}` : 'Маленькие открытия, большой мир'}</span></div>
        {#if parallel}
          <ParallelReader bind:this={comparison} source={comparisonView('source')} working={comparisonView('working')} active={version} workingName={workingBook?.working_name||'Рабочая копия'} onactivate={activatePane} onframe={comparisonReady} theme={$resolvedTheme} size={$readingSize}/>
        {:else if current?.path}
          {#key `${bookId}:${version}:${current.path}:${revision}`}<iframe bind:this={frame} title={current.title} sandbox="allow-scripts allow-downloads" allow="fullscreen *" src={`${framePath(current.path)}?v=${revision}&grim-theme=${get(resolvedTheme)}`}></iframe>{/key}
        {:else if book}
          <div class="empty-book"><span class="eyebrow">ПЕРВАЯ СТРАНИЦА ЕЩЁ ВПЕРЕДИ</span><h1>{book.title}</h1><p>Книга создана. Начните тему в чате или со своим внешним агентом: он добавит HTML-страницы и оглавление, а они появятся здесь автоматически.</p><h2>Папка для ваших страниц</h2><code>{book.root}</code><p class="small">Оглавление: book.json · Добавьте страницу в массив pages.</p></div>
        {/if}
        <footer><span class="page-stats"><span>{pageIndex+1} / {allPages.length}</span>{#if current?.path}<span class="page-characters" title="Количество знаков текста всей страницы с пробелами. Повторные пробелы и переносы строк считаются одним пробелом; HTML, стили и скрипты не учитываются.">{countedFrame===framePath(current.path) && pageCharacters!==null ? pageCharacters.toLocaleString('ru-RU') : '…'} знаков</span>{/if}</span><div class="page-navigation">{#if canReturn}<button class="return-button" onclick={returnToReading}>Вернуться</button>{/if}<button disabled={pageIndex<=0} onclick={()=>select(allPages[pageIndex-1])}>← Назад</button><button disabled={pageIndex>=allPages.length-1} onclick={()=>select(allPages[pageIndex+1])}>Далее →</button></div></footer>
      </section>
      {#if position.selection.trim() && noteSelection && selectionAnchor && !showNotes}<button class="selection-note-action" style:left={`${noteAction?.x??innerWidth/2}px`} style:top={`${noteAction?.y??innerHeight-80}px`} onclick={()=>{showNotes=true;showAgent=false;showContext=false;}}>＋ Заметка к выделению</button>{/if}
      {#if showAgent && book && !offline}{#key bookId}<AgentPanel {bookId} {readerId} {token} context={()=>({version,page_id:current?.id||null,selection:position.selection,visible_text:position.visible_text,anchor:position.anchor,viewer_revision:Math.max(0,lastRevision)})} onclose={()=>showAgent=false}/>{/key}{/if}
      {#if showNotes}<NotesPanel {notes} currentPageId={current?.id||null} selection={selectionAnchor?noteSelection:''} status={noteStatus} oncreate={createNote} onupdate={updateNote} ondelete={deleteNote} onopen={openNote} onclose={()=>showNotes=false}/>{/if}
      {#if showContext}<section class="context-panel" aria-label="Контекст чтения"><div class="panel-heading"><h2>Место в книге</h2><button aria-label="Закрыть контекст" onclick={()=>showContext=false}>×</button></div><p class="context-note">{offline ? 'Здесь видны выделенный текст и текущий фрагмент книги. Подключение к агенту появится в следующей версии.' : 'Выделите мысль на странице. Ваш внешний агент сможет прочитать её и продолжить объяснение.'}</p><div class="context-badge">{contextStatus}</div><h3>ВЫДЕЛЕННЫЙ ТЕКСТ</h3>{#if position.selection}<blockquote>{position.selection}</blockquote>{:else}<p class="empty-selection">Пока ничего не выделено</p>{/if}<h3>В ПОЛЕ ЗРЕНИЯ</h3><p class="visible-text">{position.visible_text || 'Загрузка фрагмента…'}</p>{#if !offline}<details><summary>Подключение внешнего агента</summary><p>Read-only API этой вкладки:</p><code>GET /api/context?reader_id={readerId}&amp;book_id={bookId}</code><p>Файлы книги:</p><code>{book?.root}</code></details>{/if}</section>{/if}
    </div>
  </main>
</div>

{/if}

<style>
  .book-versions { display:flex; flex-wrap:wrap; gap:6px; margin:0 18px 20px; }
  .book-versions button { font:inherit; font-size:12px; padding:8px 10px; border:1px solid currentColor; border-radius:8px; background:transparent; color:inherit; cursor:pointer; }
  .copy-controls { display:flex; min-width:0; max-width:100%; border:1px solid currentColor; border-radius:8px; }
  .book-versions .copy-version { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border:0; border-radius:7px 0 0 7px; }
  .book-versions .rename-copy { display:flex; align-items:center; justify-content:center; flex:0 0 32px; padding:8px 0; border:0; border-left:1px solid currentColor; border-radius:0 7px 7px 0; }
  .rename-copy:hover { background:color-mix(in srgb, currentColor 12%, transparent); }
  .book-versions form { width:100%; display:flex; flex-wrap:wrap; gap:6px; }
  .book-versions label { display:grid; gap:6px; font-size:12px; width:100%; }
  .book-versions input { box-sizing:border-box; width:100%; padding:8px; color:inherit; background:transparent; border:1px solid currentColor; border-radius:6px; }
  .book-versions button.chosen { font-weight:700; background:color-mix(in srgb, currentColor 12%, transparent); }
  .page-stats { display:flex; flex-wrap:wrap; gap:4px 14px; align-items:center; }
  .page-characters { white-space:nowrap; font-variant-numeric:tabular-nums; }
  .page-navigation { gap:8px; }
  .return-button { font-weight:600; }
  @media(max-width:600px) { .page-stats { flex-direction:column; align-items:flex-start; } .page-navigation { gap:0; } .page-navigation button { padding:10px 5px; } }
</style>
