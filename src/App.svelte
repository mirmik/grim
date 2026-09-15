<script lang="ts">
  import { onMount } from 'svelte';
  import Library from './Library.svelte';
  import AgentPanel from './AgentPanel.svelte';
  import { offline, fetchBook } from './platform';
  type Page = {id:string; title:string; path?:string; children?:Page[]};
  type Position = {visible_text:string; selection:string; anchor:string; scroll_y:number; anchor_offset:number};
  type Book = {id:string;title:string;subtitle?:string;pages:Page[];root:string};
  let book = $state<Book|null>(null), bookId = $state<string|null>(null);
  let current = $state<Page|null>(null), revision = $state(0), connected = $state(false), error = $state('');
  let frame = $state<HTMLIFrameElement>();
  let token = $state('');
  let lastRevision = -1, pendingHash = '', generation = 0, sequence = 0;
  let events:EventSource|null = null;
  let readerId = $state('');
  const empty = ():Position => ({visible_text:'',selection:'',anchor:'',scroll_y:0,anchor_offset:0});
  let position = $state<Position>(empty());
  let showAgent = $state(false), showContext = $state(false), sidebar = $state(false), updated = $state('');
  let contextStatus = $state('Ожидание страницы');
  const flatten = (nodes:Page[]):Page[] => nodes.flatMap(n => [...(n.path ? [n] : []), ...flatten(n.children || [])]);
  let allPages = $derived(book ? flatten(book.pages) : []);
  let pageIndex = $derived(allPages.findIndex(p=>p.id===current?.id));
  let prefix = $derived(`/book/${bookId}/`);
  const encodedPath = (path:string) => path.split('/').map(encodeURIComponent).join('/');
  function savePosition() {
    if (!book || !current) return;
    try {localStorage.setItem(`grim-reading:${book.id}`,JSON.stringify({page_id:current.id,position:{...position,selection:'',visible_text:''}}));}catch{}
  }
  function savedPosition(id:string):{page_id?:string;position?:Position} {
    try {
      const saved=JSON.parse(localStorage.getItem(`grim-reading:${id}`)||'{}');
      const p=saved.position;
      if (!p || typeof saved.page_id!=='string' || typeof p.anchor!=='string' || ![p.scroll_y,p.anchor_offset].every(Number.isFinite)) return {};
      return {page_id:saved.page_id,position:{...empty(),anchor:p.anchor,scroll_y:Math.max(0,p.scroll_y),anchor_offset:p.anchor_offset}};
    }catch{return {};}
  }
  async function publish() {
    if (!book || (!current && allPages.length)) return;
    if (offline) {contextStatus='Чтение на устройстве';return;}
    const epoch=generation;
    const payload={reader_id:readerId,sequence:++sequence,book_id:book.id,page_id:current?.id||null,...position};
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
  function select(page:Page,hash='') {
    current=page;position=empty();pendingHash=hash;sidebar=false;contextStatus='Ожидание страницы';
    savePosition();void publish();
  }
  async function loadBook(id:string,epoch:number) {
    const response=await fetchBook(id);
    if(!response.ok) throw new Error((await response.json()).detail||'Не удалось открыть книгу');
    const data=await response.json();
    if(epoch!==generation)return null;
    token=data.writer_token;
    const pages=flatten(data.pages),saved=savedPosition(id);
    const next=pages.find(p=>p.id===(current?.id||saved.page_id))||pages[0]||null;
    if(!current || current.id!==next?.id) {
      position=next && next.id===saved.page_id && saved.position ? saved.position:empty();
    }
    book=data;current=next;error='';
    if(!next)void publish();
    return data;
  }
  async function openBook(id:string,push=true) {
    savePosition();idle();events?.close();events=null;
    const epoch=++generation;
    bookId=id;book=null;current=null;position=empty();pendingHash='';error='';updated='';connected=false;sidebar=false;
    if(push)history.pushState({},'',`?book=${encodeURIComponent(id)}`);
    try {
      const data=await loadBook(id,epoch);if(!data)return;
      revision++;lastRevision=data.revision;
      if (offline) {connected=true;return;}
      const stream=new EventSource(`/api/books/${id}/events`);events=stream;
      stream.onopen=()=>{if(epoch===generation)connected=true;};
      stream.onerror=()=>{if(epoch===generation){connected=false;lastRevision=-1;}};
      stream.onmessage=async event=>{
        const message=JSON.parse(event.data);
        if(epoch!==generation || message.book_id!==id || message.revision===lastRevision)return;
        lastRevision=message.revision;
        try {
          if(await loadBook(id,epoch)) {
            revision++;updated=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
          }
        }catch(e){if(epoch===generation)error=String(e);}
      };
    }catch(e){if(epoch===generation)error=String(e);}
  }
  function showLibrary(push=true) {
    savePosition();idle();generation++;events?.close();events=null;bookId=null;book=null;current=null;error='';
    if(push)history.pushState({},'','/');
  }
  onMount(()=>{
    readerId=crypto.randomUUID();
    const navigate=()=>{
      const id=new URLSearchParams(location.search).get('book');
      if(id)void openBook(id,false);else showLibrary(false);
    };
    const listener=(event:MessageEvent)=>{
      const data=event.data;
      if(event.source!==frame?.contentWindow || !data?.grim || !current?.path || data.path!==prefix+encodedPath(current.path))return;
      if(data.type==='ready') {
        frame?.contentWindow?.postMessage({grim:true,type:'restore',position:pendingHash?{...empty(),anchor:pendingHash,anchor_offset:24}:$state.snapshot(position)},'*');pendingHash='';
      }else if(data.type==='context') {
        if(![data.visible_text,data.selection,data.anchor].every(x=>typeof x==='string') || ![data.scroll_y,data.anchor_offset].every(Number.isFinite))return;
        position={visible_text:data.visible_text.slice(0,24000),selection:data.selection.slice(0,12000),anchor:data.anchor.slice(0,300),scroll_y:Math.max(0,data.scroll_y),anchor_offset:data.anchor_offset};
        savePosition();void publish();
      }else if((data.type==='download'||data.type==='navigate') && typeof data.href==='string') {
        const url=new URL(data.href,location.origin);
        if(url.origin!==location.origin || !url.pathname.startsWith(prefix))return;
        if(data.type==='download') {
          const link=document.createElement('a');link.href=url.pathname+'?download=1';link.download='';link.click();
        }else {
          const page=allPages.find(p=>prefix+encodedPath(p.path!)===url.pathname);
          if(page)select(page,decodeURIComponent(url.hash.slice(1)));
        }
      }
    };
    const background=()=>{if(document.visibilityState==='hidden')savePosition();};
    const back=(event:Event)=>{
      if(showAgent){showAgent=false;event.preventDefault();}
      else if(showContext){showContext=false;event.preventDefault();}
      else if(sidebar){sidebar=false;event.preventDefault();}
      else if(bookId){showLibrary();event.preventDefault();}
    };
    document.addEventListener('visibilitychange',background);
    window.addEventListener('pagehide',savePosition);
    window.addEventListener('grim-back',back);
    window.addEventListener('message',listener);window.addEventListener('popstate',navigate);navigate();
    return ()=>{document.removeEventListener('visibilitychange',background);window.removeEventListener('pagehide',savePosition);window.removeEventListener('grim-back',back);generation++;events?.close();window.removeEventListener('message',listener);window.removeEventListener('popstate',navigate);};
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
<div class="app-shell" class:offline>
  <aside class:mobile-open={sidebar}>
    <a class="brand" href="/" aria-label="Grim, главная"><span class="brand-mark">g</span><span>grim<span class="brand-period">.</span></span></a>
    <button class="back-library" onclick={()=>showLibrary()}>← Библиотека</button>
    <div class="library-label">ВАША ЖИВАЯ КНИГА</div>
    <div class="book-title">{book?.title || 'Открываем книгу…'}</div>
    <p class="book-description">{book?.subtitle || 'Пространство для любопытства'}</p>
    <div class="toc-label">ОГЛАВЛЕНИЕ <span>{allPages.length.toString().padStart(2,'0')}</span></div>
    <nav aria-label="Оглавление">{#if book}{@render tree(book.pages)}{/if}</nav>
    <div class="sidebar-bottom"><div class="connection"><span class:online={connected}></span>{offline ? 'Книга на устройстве' : connected ? 'Книга обновляется с диска' : 'Восстанавливаем соединение…'}</div><p>{offline ? 'Читайте без сети. Место в книге сохраняется автоматически.' : 'Читайте. Исследуйте. Задавайте вопросы своему агенту.'}</p><span class="version">GRIM / PROTOTYPE 0.2</span></div>
  </aside>
  <main>
    <header><button class="menu-button" aria-label="Оглавление" onclick={()=>sidebar=!sidebar}>☰</button><div class="breadcrumbs"><button class="breadcrumb-library" onclick={()=>showLibrary()}>Библиотека</button> <span>/</span> <strong>{current?.title || 'Grim'}</strong></div><button class="context-toggle" class:selected={showContext} onclick={()=>{showContext=!showContext;showAgent=false;}}><span>⌘</span> <span class="context-label">{offline ? 'Фрагмент' : 'Контекст чтения'}</span> {#if position.selection}<i></i>{/if}</button>{#if !offline && book}<button class="context-toggle" class:selected={showAgent} onclick={()=>{showAgent=!showAgent;showContext=false;}}>Чат с агентом</button>{/if}</header>
    {#if error}<div class="error" role="alert">{error}</div>{/if}
    <div class="reading-area">
      <section class="page-area" aria-label="Страница книги">
        <div class="reading-meta"><span>{current ? 'ГЛАВА '+(pageIndex+1).toString().padStart(2,'0') : 'НОВАЯ КНИГА'}</span><span>{updated ? `Обновлено в ${updated}` : 'Маленькие открытия, большой мир'}</span></div>
        {#if current?.path}
          {#key `${bookId}:${current.path}:${revision}`}<iframe bind:this={frame} title={current.title} sandbox="allow-scripts allow-downloads" allow="fullscreen *" src={`${prefix}${encodedPath(current.path)}?v=${revision}`}></iframe>{/key}
        {:else if book}
          <div class="empty-book"><span class="eyebrow">ПЕРВАЯ СТРАНИЦА ЕЩЁ ВПЕРЕДИ</span><h1>{book.title}</h1><p>Книга создана. Начните тему в чате или со своим внешним агентом: он добавит HTML-страницы и оглавление, а они появятся здесь автоматически.</p><h2>Папка для ваших страниц</h2><code>{book.root}</code><p class="small">Оглавление: book.json · Добавьте страницу в массив pages.</p></div>
        {/if}
        <footer><span>{pageIndex+1} / {allPages.length}</span><div><button disabled={pageIndex<=0} onclick={()=>select(allPages[pageIndex-1])}>← Назад</button><button disabled={pageIndex>=allPages.length-1} onclick={()=>select(allPages[pageIndex+1])}>Далее →</button></div></footer>
      </section>
      {#if showAgent && book && !offline}{#key bookId}<AgentPanel {bookId} {readerId} {token} context={()=>({page_id:current?.id||null,selection:position.selection,visible_text:position.visible_text,anchor:position.anchor,viewer_revision:Math.max(0,lastRevision)})} onclose={()=>showAgent=false}/>{/key}{/if}
      {#if showContext}<section class="context-panel" aria-label="Контекст чтения"><div class="panel-heading"><h2>Место в книге</h2><button aria-label="Закрыть контекст" onclick={()=>showContext=false}>×</button></div><p class="context-note">{offline ? 'Здесь видны выделенный текст и текущий фрагмент книги. Подключение к агенту появится в следующей версии.' : 'Выделите мысль на странице. Ваш внешний агент сможет прочитать её и продолжить объяснение.'}</p><div class="context-badge">{contextStatus}</div><h3>ВЫДЕЛЕННЫЙ ТЕКСТ</h3>{#if position.selection}<blockquote>{position.selection}</blockquote>{:else}<p class="empty-selection">Пока ничего не выделено</p>{/if}<h3>В ПОЛЕ ЗРЕНИЯ</h3><p class="visible-text">{position.visible_text || 'Загрузка фрагмента…'}</p>{#if !offline}<details><summary>Подключение внешнего агента</summary><p>Read-only API этой вкладки:</p><code>GET /api/context?reader_id={readerId}&amp;book_id={bookId}</code><p>Файлы книги:</p><code>{book?.root}</code></details>{/if}</section>{/if}
    </div>
  </main>
</div>

{/if}
