<script lang="ts">
  import { onMount } from 'svelte';
  type Context = {page_id:string|null;selection:string;visible_text:string;anchor:string;viewer_revision:number};
  type Job = {id:string;message:string;response:string;status:string;error:string;context:Context;events:{name:string;detail:string}[]};
  type Settings = {endpoint:string;model:string;system_prompt:string;max_tokens:number;max_iterations:number;timeout_seconds:number;has_token:boolean;runtime_available:boolean};
  let {bookId, readerId, token, context, onclose}: {bookId:string;readerId:string;token:string;context:()=>Context;onclose:()=>void} = $props();
  let jobs = $state<Job[]>([]), settings = $state<Settings|null>(null);
  let draft = $state(''), error = $state(''), notice = $state(''), apiToken = $state(''), clearToken = $state(false);
  let configuring = $state(false), sending = $state(false), saving = $state(false), loading = $state(true);
  let alive = true, refreshing = false;
  let pending: {job_id:string;message:string;reader_id:string;context:Context}|null = null;
  const active = (job:Job) => ['queued','running','stopping'].includes(job.status);
  let busy = $derived(jobs.some(active));
  const toolLabels: Record<string,string> = {reading_context:'Смотрит контекст чтения',book_read:'Читает книгу',book_search:'Ищет в книге',book_write:'Сохраняет файл',book_replace:'Изменяет фрагмент',book_guidance:'Читает руководство'};
  const statuses: Record<string,string> = {queued:'В очереди',running:'Агент работает…',stopping:'Останавливаем после текущего действия…',cancelled:'Остановлено',failed:'Не удалось завершить',interrupted:'Задание прервано перезапуском'};
  class ApiError extends Error {
    status:number;
    constructor(message:string, status:number) {super(message);this.status=status;}
  }
  async function api(url:string, method='GET', body?:unknown) {
    const response=await fetch(url,{method,headers:{'Content-Type':'application/json','X-Grim-Viewer':token},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await response.json();
    if(!response.ok)throw new ApiError(typeof data.detail==='string'?data.detail:`Ошибка запроса (${response.status})`,response.status);
    return data;
  }
  async function refresh() {
    if(refreshing)return;
    refreshing=true;
    try {
      const data=await api(`/api/books/${bookId}/agent`);
      if(alive) {
        jobs=data.jobs;
        if(pending && jobs.some(job=>job.id===pending?.job_id)) {if(draft===pending.message)draft='';pending=null;error='';}
      }
    } catch(e) {if(alive)error=String(e);} finally {refreshing=false;loading=false;}
  }
  async function send(event?:SubmitEvent) {
    event?.preventDefault();
    if(sending||busy||!draft.trim()||!settings?.runtime_available)return;
    sending=true;error='';
    // A retry after a lost response keeps the ID and original context snapshot.
    if(!pending || pending.message!==draft.trim())pending={job_id:crypto.randomUUID(),message:draft.trim(),reader_id:readerId,context:context()};
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
  async function saveSettings(event:SubmitEvent) {
    event.preventDefault();if(!settings)return;
    saving=true;error='';notice='';
    try {
      const data=await api('/api/agent/settings','PUT',{...settings,api_token:apiToken||null,clear_token:clearToken});
      if(alive){settings=data;apiToken='';clearToken=false;notice='Настройки сохранены';}
    } catch(e) {if(alive)error=String(e);} finally {saving=false;}
  }
  async function probe() {
    error='';notice='';saving=true;
    try {
      const data=await api('/api/agent/probe','POST');
      if(alive)notice=data.models.length?`Доступные модели: ${data.models.join(', ')}`:'Сервер ответил, список моделей пуст';
    } catch(e) {if(alive)error=String(e);} finally {saving=false;}
  }
  async function stop(job:Job) {
    try{await api(`/api/books/${bookId}/agent/jobs/${job.id}/stop`,'POST');await refresh();}
    catch(e){if(alive)error=String(e);}
  }
  onMount(()=>{
    alive=true;
    void api('/api/agent/settings').then(data=>{if(alive){settings=data;configuring=!data.model;}}).catch(e=>{if(alive)error=String(e);});
    void refresh();
    const interval=setInterval(()=>{void refresh();},1000);
    return ()=>{alive=false;clearInterval(interval);};
  });
</script>

<section class="agent-panel" aria-label="Книжный агент">
  <div class="panel-heading"><h2>Книжный агент</h2><div><button aria-label="Настройки агента" onclick={()=>configuring=!configuring}>⚙</button><button aria-label="Закрыть чат" onclick={onclose}>×</button></div></div>
  {#if settings && !settings.runtime_available}<p class="agent-note">Локальный агент ещё не установлен на сервере. Установка описана в docs/local-agent.md. Внешний агент может работать как прежде.</p>{/if}
  {#if error}<div class="error" role="alert">{error}</div>{/if}
  {#if notice}<p class="agent-notice" role="status">{notice}</p>{/if}
  {#if configuring && settings}
    <form class="agent-settings" onsubmit={saveSettings}>
      <label for="agent-endpoint">Адрес сервера модели</label><input id="agent-endpoint" type="url" bind:value={settings.endpoint} required placeholder="http://127.0.0.1:8080/v1">
      <label for="agent-model">Имя модели</label><input id="agent-model" bind:value={settings.model} placeholder="Имя из списка моделей" required>
      <label for="agent-token">API-токен {settings.has_token?'(сохранён)':''}</label><input id="agent-token" type="password" bind:value={apiToken} autocomplete="new-password" placeholder="Оставьте пустым, чтобы сохранить прежний">
      {#if settings.has_token}<label class="agent-check"><input type="checkbox" bind:checked={clearToken}> Удалить сохранённый токен</label>{/if}
      <details><summary>Настройки ответа</summary>
        <label for="agent-prompt">Указания агенту</label><textarea id="agent-prompt" bind:value={settings.system_prompt} rows="4"></textarea>
        <label for="agent-tokens">Максимум токенов ответа</label><input id="agent-tokens" type="number" min="128" max="65536" bind:value={settings.max_tokens}>
        <label for="agent-iterations">Максимум шагов агента</label><input id="agent-iterations" type="number" min="1" max="64" bind:value={settings.max_iterations}>
        <label for="agent-timeout">Ожидание модели, секунды</label><input id="agent-timeout" type="number" min="5" max="3600" bind:value={settings.timeout_seconds}>
      </details>
      <div class="agent-actions"><button type="submit" disabled={saving}>Сохранить</button><button type="button" onclick={probe} disabled={saving}>Проверить сохранённое подключение</button></div>
    </form>
  {:else}
    <div class="agent-conversation" aria-live="polite">
      {#if loading}<p class="agent-note">Загружаем разговор…</p>{:else if !jobs.length}<p class="agent-note">Обсудите прочитанное или попросите дополнить книгу. Агент видит выбранный фрагмент и может менять её страницы.</p>{/if}
      {#each jobs as job (job.id)}
        <article class="agent-turn"><h3>Вы</h3><p class="agent-message">{job.message}</p>
          {#if job.context.selection}<details><summary>Фрагмент из книги</summary><blockquote>{job.context.selection}</blockquote></details>{/if}
          <h3>Агент</h3>
          {#if job.response}<p class="agent-message">{job.response}</p>{/if}
          {#if active(job)}<p class="agent-note">{statuses[job.status]} {job.status==='running' && job.events.length?toolLabels[job.events.at(-1)!.name]||'':''}</p><button class="agent-stop" onclick={()=>stop(job)} disabled={job.status==='stopping'}>Остановить</button>
          {:else if job.status!=='completed'}<p class="agent-note">{statuses[job.status]}</p>{/if}
          {#if job.error}<p class="error">{job.error}</p>{/if}
        </article>
      {/each}
    </div>
    <form class="agent-compose" onsubmit={send}>
      <label class="agent-note" for="agent-message">Сообщение о текущей книге</label>
      <textarea id="agent-message" bind:value={draft} rows="3" placeholder="Объясни этот фрагмент или добавь пример…" disabled={sending} onkeydown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void send();}}}></textarea>
      <button type="submit" disabled={sending||busy||!draft.trim()||!settings?.runtime_available||!settings?.model}>{sending?'Отправляем…':'Отправить'}</button>
    </form>
  {/if}
</section>

<style>
  .agent-panel{width:390px;flex-shrink:0;padding:24px;border-left:1px solid #e3e7da;background:#f8f9f2;display:flex;flex-direction:column;min-height:0;overflow:auto}
  .panel-heading{gap:12px;margin-bottom:12px}.panel-heading div{display:flex}.panel-heading button{min-width:36px;min-height:36px}
  .agent-note,.agent-notice{font-size:12px;line-height:1.6;color:#66765d}.agent-notice{overflow-wrap:anywhere}
  .agent-conversation{flex:1;overflow:auto;min-height:100px}.agent-turn{padding:8px 0 20px;border-bottom:1px solid #dfe5d4}.agent-turn h3{font-size:11px;color:#617852;margin:16px 0 8px}.agent-message{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui,sans-serif;margin:0}.agent-turn blockquote{margin:12px 0;white-space:pre-wrap;border-left:2px solid #8da765;padding-left:12px;font:14px/1.7 Georgia,serif}.agent-turn details{margin-top:12px;padding-top:10px}
  .agent-compose{padding-top:16px}.agent-compose label{display:block;margin-bottom:6px}.agent-panel textarea,.agent-panel input:not([type=checkbox]){box-sizing:border-box;width:100%;font:13px/1.5 system-ui,sans-serif;background:#fffefa;color:#304c32;border:1px solid #cedbbb;border-radius:5px;padding:9px}.agent-panel textarea{resize:vertical;min-height:60px}
  .agent-panel form button,.agent-stop{border:1px solid #cbd8bc;border-radius:5px;background:#eef3e5;color:#355b3b;padding:9px 12px;font:12px system-ui,sans-serif}.agent-compose button{margin-top:8px;background:#325941!important;color:#fffefa!important;width:100%}
  .agent-settings label{display:block;font-size:12px;margin:12px 0 6px}.agent-settings details{margin-top:16px;padding-top:12px}.agent-check{display:flex!important;align-items:center;gap:8px}.agent-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.agent-stop{padding:5px 10px}
  @media(max-width:1100px){.agent-panel{position:absolute;right:0;top:76px;bottom:0;z-index:7;width:min(390px,100vw);box-sizing:border-box;box-shadow:-5px 0 25px #24362115}}
  @media(max-width:720px),(max-height:500px) and (pointer:coarse){.agent-panel{top:65px;padding:16px}}
</style>
