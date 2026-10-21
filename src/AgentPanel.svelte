<script lang="ts">
  import { onMount, type ComponentProps } from 'svelte';
  import AgentContext from './AgentContext.svelte';
  import AgentMessage from './AgentMessage.svelte';
  type Context = {version:'working'|'source';page_id:string|null;selection:string;visible_text:string;anchor:string;viewer_revision:number};
  type Job = {id:string;chat_id:string;kind?:string;message:string;response:string;status:string;error:string;context:Context;events:{name:string;detail:string}[]};
  type Chat = {id:string;title:string;created_at:number;updated_at:number;job_count:number};
  type Settings = {endpoint:string;tls_fingerprint:string;model:string;system_prompt:string;max_tokens:number;max_iterations:number;timeout_seconds:number;has_token:boolean;runtime_available:boolean};
  let {bookId, readerId, token, context, onclose}: {bookId:string;readerId:string;token:string;context:()=>Context;onclose:()=>void} = $props();
  let jobs = $state<Job[]>([]), settings = $state<Settings|null>(null);
  let draft = $state(''), error = $state(''), notice = $state(''), apiToken = $state(''), clearToken = $state(false);
  let configuring = $state(false), sending = $state(false), saving = $state(false), loading = $state(true);
  let alive = true, refreshing = false;
  let chatId=$state(''), chats=$state<Chat[]>([]), runningChatId=$state<string|null>(null);
  let showChats=$state(false), switching=$state(false), showDebug=$state(false), debugLoading=$state(false);
  let debugData=$state<ComponentProps<typeof AgentContext>['data']|null>(null);
  const drafts=new Map<string,string>();
  let chatEpoch=0, debugEpoch=0;
  let pending=$state.raw<{job_id:string;chat_id:string;message:string;reader_id:string;context:Context}|null>(null);
  let maintenance=$state<'compact'|'system'|''>('');
  let pendingCompact=$state.raw<{job_id:string;chat_id:string}|null>(null);
  const active = (job:Job) => ['queued','running','stopping'].includes(job.status);
  let busy = $derived(!!runningChatId || jobs.some(active));
  function rememberChat(id:string) {
    chatId=id;
    try{sessionStorage.setItem(`grim-agent-chat:${bookId}`,id);}catch{}
  }
  const toolLabels: Record<string,string> = {reading_context:'Смотрит контекст чтения',book_read:'Читает книгу',book_search:'Ищет в книге',book_write:'Сохраняет файл',book_replace:'Изменяет фрагмент',book_guidance:'Читает руководство',notes_list:'Смотрит список записок',notes_read:'Читает записку',notes_create:'Создаёт записку',notes_update:'Обновляет записку',notes_delete:'Удаляет записку',web_search:'Ищет в интернете',fetch_webpage:'Читает веб-страницу'};
  const statuses: Record<string,string> = {queued:'В очереди',running:'Агент работает…',stopping:'Останавливаем после текущего действия…',cancelled:'Остановлено',failed:'Не удалось завершить',interrupted:'Задание прервано перезапуском'};
  class ApiError extends Error {
    status:number;
    constructor(message:string, status:number) {super(message);this.status=status;}
  }
  async function api(url:string, method='GET', body?:unknown) {
    const response=await fetch(url,{method,headers:{'Content-Type':'application/json','X-Grim-Viewer':token},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await response.json();
    if(!response.ok) {
      const validation=Array.isArray(data.detail)?data.detail.map((item:{msg?:string})=>item.msg?.replace(/^Value error, /,'')).filter(Boolean).join('; '):'';
      throw new ApiError(typeof data.detail==='string'?data.detail:validation||`Ошибка запроса (${response.status})`,response.status);
    }
    return data;
  }
  async function refresh() {
    if(refreshing)return;
    refreshing=true;
    const epoch=chatEpoch;
    try {
      const data=await api(`/api/books/${bookId}/agent${chatId?'?chat_id='+encodeURIComponent(chatId):''}`);
      if(alive && epoch===chatEpoch) {
        rememberChat(data.chat.id);chats=data.chats;runningChatId=data.running_chat_id;jobs=data.jobs;
        if(pending && jobs.some(job=>job.id===pending?.job_id)) {if(draft===pending.message)draft='';pending=null;error='';}
        if(pendingCompact && jobs.some(job=>job.id===pendingCompact?.job_id)){pendingCompact=null;error='';}
      }
    } catch(e) {if(alive && epoch===chatEpoch)error=String(e);} finally {refreshing=false;loading=false;}
  }
  async function chooseChat(id?:string) {
    if(switching||sending||pending||maintenance||pendingCompact)return;
    switching=true;error='';const epoch=++chatEpoch;
    drafts.set(chatId,draft);
    try {
      const data=await api(`/api/books/${bookId}/agent/chats${id?'/'+encodeURIComponent(id)+'/activate':''}`,'POST');
      if(!alive || epoch!==chatEpoch)return;
      rememberChat(data.chat.id);chats=data.chats;jobs=data.jobs;runningChatId=data.running_chat_id;
      draft=drafts.get(chatId)||'';showChats=false;showDebug=false;debugData=null;debugEpoch++;debugLoading=false;notice='';
    }catch(e){if(alive)error=String(e);}finally{switching=false;}
  }
  async function inspectContext() {
    if(!chatId)return;
    showDebug=true;configuring=false;showChats=false;debugLoading=true;error='';
    const epoch=++debugEpoch,selectedChat=chatId;
    try {
      const data=await api(`/api/books/${bookId}/agent/context`,'POST',{chat_id:chatId,reader_id:readerId,message:draft,context:context()});
      if(alive && selectedChat===chatId && epoch===debugEpoch)debugData=data;
    }catch(e){if(alive && epoch===debugEpoch)error=String(e);}finally{if(epoch===debugEpoch)debugLoading=false;}
  }
  async function send(event?:SubmitEvent) {
    event?.preventDefault();
    if(sending||switching||busy||maintenance||pendingCompact||!chatId||!draft.trim()||!settings?.runtime_available)return;
    sending=true;error='';
    // A retry after a lost response keeps the ID and original context snapshot.
    if(!pending || pending.message!==draft.trim() || pending.chat_id!==chatId)pending={job_id:crypto.randomUUID(),chat_id:chatId,message:draft.trim(),reader_id:readerId,context:context()};
    try {
      await api(`/api/books/${bookId}/agent/jobs`,'POST',pending);
      if(alive){draft='';pending=null;await refresh();}
    } catch(e) {
      // A definitive rejection permits a fresh snapshot after fixing the page
      // or settings. Only uncertain delivery needs the old request identity.
      if(e instanceof ApiError && e.status>=400 && e.status<500)pending=null;
      if(alive)error=String(e);
    } finally {sending=false;}
  }
  async function maintain(kind:'compact'|'system') {
    if(!chatId||busy||maintenance||switching||sending||pending||(pendingCompact&&kind==='system'))return;
    maintenance=kind;error='';notice='';
    const selectedChat=chatId;
    try {
      if(kind==='compact') {
        pendingCompact??={job_id:crypto.randomUUID(),chat_id:chatId};
        await api(`/api/books/${bookId}/agent/chats/${encodeURIComponent(pendingCompact.chat_id)}/compact`,'POST',{job_id:pendingCompact.job_id});
        pendingCompact=null;notice='Компактизация запущена. Последние два обмена останутся целиком.';
      } else {
        const result=await api(`/api/books/${bookId}/agent/chats/${encodeURIComponent(chatId)}/refresh-system`,'POST');
        notice=result.message;
      }
      await refresh();
      if(showDebug && selectedChat===chatId)await inspectContext();
    }catch(e){
      const rejected=e instanceof ApiError && e.status>=400 && e.status<500;
      if(rejected)pendingCompact=null;
      // Polling may already have confirmed acceptance before a lost POST
      // response reaches this catch. Keep the confirmed operation visible.
      if(alive && !(kind==='compact' && !rejected && !pendingCompact))error=String(e);
    }finally{maintenance='';}
  }
  async function saveSettings(event:SubmitEvent) {
    event.preventDefault();if(!settings)return;
    saving=true;error='';notice='';
    try {
      const data=await api('/api/agent/settings','PUT',{...settings,api_token:apiToken||null,clear_token:clearToken});
      if(alive){settings=data;apiToken='';clearToken=false;notice='Настройки сохранены';}
      if((event.submitter as HTMLButtonElement|null)?.value==='probe') {
        const result=await api('/api/agent/probe','POST');
        if(alive)notice=result.models.length?`Доступные модели: ${result.models.join(', ')}`:'Сервер ответил, список моделей пуст';
      }
    } catch(e) {if(alive)error=String(e);} finally {saving=false;}
  }
  async function stop(job:Job) {
    try{await api(`/api/books/${bookId}/agent/jobs/${job.id}/stop`,'POST');await refresh();}
    catch(e){if(alive)error=String(e);}
  }
  onMount(()=>{
    alive=true;
    try{chatId=sessionStorage.getItem(`grim-agent-chat:${bookId}`)||'';}catch{}
    void api('/api/agent/settings').then(data=>{if(alive){settings=data;configuring=!data.model;}}).catch(e=>{if(alive)error=String(e);});
    void refresh();
    const interval=setInterval(()=>{void refresh();},1000);
    return ()=>{alive=false;chatEpoch++;debugEpoch++;clearInterval(interval);};
  });
</script>

<section class="agent-panel" aria-label="Книжный агент">
  <div class="panel-heading"><h2>Книжный агент</h2><div><button aria-label="Настройки агента" onclick={()=>{configuring=!configuring;showDebug=false;}}>⚙</button><button aria-label="Закрыть чат" onclick={onclose}>×</button></div></div>
  <div class="chat-controls">
    <button disabled={switching||sending||!!pending||!!maintenance||!!pendingCompact||!chatId} onclick={()=>chooseChat()}>Начать новый чат</button>
    <button aria-expanded={showChats} disabled={switching||!!maintenance||!!pendingCompact||!chatId} onclick={()=>{showChats=!showChats;showDebug=false;}}>Старые чаты</button>
    <button disabled={!chatId||debugLoading} onclick={inspectContext}>Контекст агента</button>
    <button disabled={!chatId||busy||!!maintenance||switching||sending||!!pending||!settings?.runtime_available||!settings?.model} title="Сводка старого контекста; последние два обмена остаются целиком. Вызывает модель." onclick={()=>maintain('compact')}>{maintenance==='compact'?'Запускаем сжатие…':pendingCompact?'Повторить запрос сжатия':'Компактизировать чат'}</button>
    <button disabled={!chatId||busy||!!maintenance||switching||sending||!!pending||!!pendingCompact} title="Применить актуальные правила Grim и сохранённые указания агента без вызова модели." onclick={()=>maintain('system')}>{maintenance==='system'?'Обновляем инструкции…':'Обновить системные инструкции'}</button>
  </div>
  {#if showChats}<nav class="chat-list" aria-label="Чаты этой книги">
    {#each chats as chat}<button class:current={chat.id===chatId} aria-current={chat.id===chatId?'true':undefined} disabled={switching||sending||!!pending||!!maintenance||!!pendingCompact} onclick={()=>chooseChat(chat.id)}><strong>{chat.title}</strong><span>{new Date(chat.created_at*1000).toLocaleString('ru-RU')}{chat.id===runningChatId?' · Агент работает':''}</span></button>{/each}
  </nav>{/if}
  {#if settings && !settings.runtime_available}<p class="agent-note">Локальный агент ещё не установлен на сервере. Установка описана в docs/local-agent.md. Внешний агент может работать как прежде.</p>{/if}
  {#if error}<div class="error" role="alert">{error}</div>{/if}
  {#if notice}<p class="agent-notice" role="status">{notice}</p>{/if}
  {#if showDebug}
    {#if debugData}<AgentContext data={debugData} loading={debugLoading} onrefresh={inspectContext} onclose={()=>{showDebug=false;debugEpoch++;debugLoading=false;}}/>{:else if debugLoading}<p class="agent-note">Загружаем контекст…</p>{:else}<button onclick={()=>showDebug=false}>Вернуться к чату</button>{/if}
  {:else if configuring && settings}
    <form class="agent-settings" onsubmit={saveSettings}>
      <label for="agent-endpoint">Адрес сервера модели</label><input id="agent-endpoint" type="url" bind:value={settings.endpoint} required placeholder="http://127.0.0.1:8080/v1">
      <label for="agent-fingerprint">Fingerprint сертификата SHA-256</label><input id="agent-fingerprint" bind:value={settings.tls_fingerprint} maxlength="256" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="Необязательно · 64 hex или AA:BB:…" aria-describedby="agent-fingerprint-help">
      <p id="agent-fingerprint-help" class="agent-note">Для частного HTTPS-сервера укажите fingerprint, полученный у его владельца. Он проверяется вместо центра сертификации и имени сервера. Пустое поле — обычная проверка HTTPS.</p>
      <label for="agent-model">Имя модели</label><input id="agent-model" bind:value={settings.model} placeholder="Имя из списка моделей" required>
      <label for="agent-token">API-токен {settings.has_token?'(сохранён)':''}</label><input id="agent-token" class="masked-token" type="text" bind:value={apiToken} autocomplete="off" autocapitalize="none" spellcheck="false" data-1p-ignore data-lpignore="true" placeholder="Оставьте пустым, чтобы сохранить прежний">
      {#if settings.has_token}<label class="agent-check"><input type="checkbox" bind:checked={clearToken}> Удалить сохранённый токен</label>{/if}
      <details><summary>Настройки ответа</summary>
        <label for="agent-prompt">Указания агенту</label><textarea id="agent-prompt" bind:value={settings.system_prompt} rows="4"></textarea>
        <label for="agent-tokens">Максимум токенов ответа</label><input id="agent-tokens" type="number" min="128" max="65536" bind:value={settings.max_tokens}>
        <label for="agent-iterations">Максимум шагов агента</label><input id="agent-iterations" type="number" min="1" max="64" bind:value={settings.max_iterations}>
        <label for="agent-timeout">Ожидание модели, секунды</label><input id="agent-timeout" type="number" min="5" max="3600" bind:value={settings.timeout_seconds}>
      </details>
      <div class="agent-actions"><button type="submit" disabled={saving}>Сохранить</button><button type="submit" value="probe" disabled={saving}>Сохранить и проверить</button></div>
    </form>
  {:else}
    {#if runningChatId && runningChatId!==chatId}<p class="agent-note">Агент ещё работает в другом чате этой книги. <button onclick={()=>chooseChat(runningChatId!)}>Открыть выполняющийся чат</button></p>{/if}
    <div class="agent-conversation" aria-live="polite">
      {#if loading}<p class="agent-note">Загружаем разговор…</p>{:else if !jobs.length}<p class="agent-note">Обсудите прочитанное или попросите дополнить книгу. Агент видит выбранный фрагмент и может менять её страницы.</p>{/if}
      {#each jobs as job (job.id)}
        <article class="agent-turn"><h3>{job.kind==='compact'?'Контекст чата':'Вы'}</h3><p class="agent-message">{job.message}</p>
          {#if job.context.selection}<details><summary>Фрагмент из книги</summary><blockquote>{job.context.selection}</blockquote></details>{/if}
          <h3>Агент</h3>
          {#if job.response}<div class="agent-message"><AgentMessage text={job.response}/></div>{/if}
          {#if active(job)}<p class="agent-note">{job.kind==='compact'?'Сжимаем контекст…':statuses[job.status]} {job.status==='running' && job.events.length?toolLabels[job.events.at(-1)!.name]||'':''}</p><button class="agent-stop" onclick={()=>stop(job)} disabled={job.status==='stopping'}>Остановить</button>
          {:else if job.status!=='completed'}<p class="agent-note">{statuses[job.status]}</p>{/if}
          {#if job.error}<p class="error">{job.error}</p>{/if}
        </article>
      {/each}
    </div>
    <form class="agent-compose" onsubmit={send}>
      <label class="agent-note" for="agent-message">Сообщение о текущей книге</label>
      <textarea id="agent-message" bind:value={draft} rows="3" placeholder="Объясни этот фрагмент или добавь пример…" disabled={sending} onkeydown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void send();}}}></textarea>
      <button type="submit" disabled={sending||switching||busy||!!maintenance||!!pendingCompact||!chatId||!draft.trim()||!settings?.runtime_available||!settings?.model}>{sending?'Отправляем…':'Отправить'}</button>
    </form>
  {/if}
</section>

<style>
  .agent-panel{width:390px;flex-shrink:0;padding:24px;border-left:1px solid var(--border, #e3e7da);background:var(--panel, #f8f9f2);display:flex;flex-direction:column;min-height:0;overflow:auto}
  .chat-controls{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}.chat-controls button{border:1px solid var(--border,#cbd8bc);border-radius:5px;background:var(--panel,#f8f9f2);color:var(--text,#355b3b);padding:8px;font-size:11px;min-height:36px}
  .chat-list{flex-shrink:0;max-height:240px;overflow:auto;margin-bottom:12px}.chat-list button{display:block;width:100%;text-align:left;border:1px solid var(--border,#cbd8bc);border-radius:5px;background:var(--surface,#fffefa);color:var(--text,#355b3b);padding:10px;margin-bottom:6px;overflow-wrap:anywhere}.chat-list .current{background:var(--hover,#eef3e5);border-color:var(--focus,#477b61)}.chat-list strong{display:block;font-size:12px;font-weight:500}.chat-list span{display:block;font-size:10px;margin-top:5px;color:var(--muted,#66765d)}
  .panel-heading{gap:12px;margin-bottom:12px}.panel-heading div{display:flex}.panel-heading button{min-width:36px;min-height:36px}
  .agent-note,.agent-notice{font-size:12px;line-height:1.6;color:var(--muted, #66765d)}.agent-notice{overflow-wrap:anywhere}
  .agent-conversation{flex:1;overflow:auto;min-height:100px}.agent-turn{padding:8px 0 20px;border-bottom:1px solid var(--border, #dfe5d4)}.agent-turn h3{font-size:11px;color:var(--muted, #617852);margin:16px 0 8px}.agent-message{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui,sans-serif;margin:0}.agent-turn blockquote{margin:12px 0;white-space:pre-wrap;border-left:2px solid var(--border, #8da765);padding-left:12px;font:14px/1.7 Georgia,serif}.agent-turn details{margin-top:12px;padding-top:10px}
  .agent-compose{padding-top:16px}.agent-compose label{display:block;margin-bottom:6px}.agent-panel textarea,.agent-panel input:not([type=checkbox]){box-sizing:border-box;width:100%;font:13px/1.5 system-ui,sans-serif;background:var(--surface, #fffefa);color:var(--text, #304c32);border:1px solid var(--border, #cedbbb);border-radius:5px;padding:9px}.agent-panel textarea{resize:vertical;min-height:60px}
  .agent-panel form button,.agent-stop{border:1px solid var(--border, #cbd8bc);border-radius:5px;background:var(--hover, #eef3e5);color:var(--text, #355b3b);padding:9px 12px;font:12px system-ui,sans-serif}.agent-compose button{margin-top:8px;background:var(--primary, #325941)!important;color:var(--on-primary, #fffefa)!important;width:100%}
  .agent-settings label{display:block;font-size:12px;margin:12px 0 6px}.agent-settings details{margin-top:16px;padding-top:12px}.agent-check{display:flex!important;align-items:center;gap:8px}.agent-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.agent-stop{padding:5px 10px}
  .masked-token{-webkit-text-security:disc}
  @media(max-width:1100px){.agent-panel{position:absolute;right:0;top:76px;bottom:0;z-index:7;width:min(390px,100vw);box-sizing:border-box;box-shadow:-5px 0 25px #24362115}}
  @media(max-width:720px),(max-height:500px) and (pointer:coarse){.agent-panel{top:65px;padding:16px}}
</style>
