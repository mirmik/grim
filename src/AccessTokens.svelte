<script lang="ts">
  import { onMount } from 'svelte';
  let { onclose }: { onclose: () => void } = $props();
  type DeviceToken = {id:string;name:string;prefix:string;created_at:number;last_used_at:number|null;revoked_at:number|null};
  let entries = $state<DeviceToken[]>([]), name = $state(''), raw = $state(''), createdId = $state('');
  let error = $state(''), busy = $state(false), loading = $state(true), confirmId = $state(''), copyMessage = $state('');
  let secretInput = $state<HTMLInputElement>();
  async function request(path:string, method='GET', body?:object) {
    const bootstrap = await fetch('/api/library', {cache:'no-store'});
    if (!bootstrap.ok) throw new Error('Нет соединения с библиотекой');
    const library = await bootstrap.json();
    if (!library.can_manage_access) throw new Error('Откройте управление доступом в основной веб-библиотеке');
    const response = await fetch(path, {method, cache:'no-store', headers:{
      'X-Grim-Viewer':library.writer_token, ...(body ? {'Content-Type':'application/json'} : {})
    }, body:body ? JSON.stringify(body) : undefined});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : 'Не удалось изменить токены');
    return data;
  }
  async function refresh() {
    try { entries=(await request('/api/access-tokens')).tokens; }
    catch(e) { error=(e as Error).message; }
    finally { loading=false; }
  }
  async function create(event:SubmitEvent) {
    event.preventDefault(); if (busy) return;
    busy=true; error=''; raw=''; copyMessage='';
    try {
      const result=await request('/api/access-tokens','POST',{name:name.trim()});
      raw=result.token;createdId=result.entry.id;name='';await refresh();
    } catch(e) { error=(e as Error).message; }
    finally { busy=false; }
  }
  async function revoke(id:string) {
    if (busy) return;
    busy=true;error='';
    try {
      await request(`/api/access-tokens/${encodeURIComponent(id)}`,'DELETE');
      if (id===createdId) {raw='';createdId='';}
      confirmId='';await refresh();
    } catch(e) { error=(e as Error).message; }
    finally { busy=false; }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(raw);copyMessage='Токен скопирован'; }
    catch { secretInput?.focus();secretInput?.select();copyMessage='Токен выделен — скопируйте его'; }
  }
  function date(value:number|null) {
    return value ? new Date(value*1000).toLocaleString('ru-RU',{dateStyle:'short',timeStyle:'short'}) : 'ещё не использовался';
  }
  onMount(()=>{void refresh();});
</script>

<section class="access-panel" aria-labelledby="access-heading">
  <div class="panel-heading"><h2 id="access-heading">Токены доступа</h2><button type="button" aria-label="Закрыть токены доступа" disabled={busy} onclick={onclose}>×</button></div>
  <p>Создайте отдельный токен для каждого устройства. Его можно отозвать, сохранив доступ на остальных.</p>
  <form onsubmit={create}>
    <label for="device-name">Название устройства</label>
    <div class="create-fields"><input id="device-name" bind:value={name} maxlength="80" placeholder="Например, Основной смартфон" required disabled={busy}><button class="primary" disabled={busy || !name.trim()}>Создать токен</button></div>
  </form>
  {#if raw}
    <div class="new-token" role="region" aria-label="Новый токен">
      <p><strong>Скопируйте токен сейчас.</strong> После закрытия панели показать его снова не получится.</p>
      <label for="new-access-token">Токен для входа</label>
      <div class="create-fields"><input id="new-access-token" bind:this={secretInput} value={raw} readonly spellcheck="false" autocomplete="off"><button type="button" onclick={copy}>Скопировать токен</button></div>
      <p class="copy-status" role="status">{copyMessage}</p>
    </div>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if loading}<p>Загружаем токены…</p>{:else}
    <ul aria-label="Токены устройств">
      {#each entries as entry (entry.id)}
        <li class:revoked={entry.revoked_at!==null}>
          <div class="token-info"><strong>{entry.name}</strong><span>{entry.revoked_at!==null ? 'Отозван' : 'Действует'}{entry.prefix ? ` · ${entry.prefix}…` : ''}</span><small>Создан {date(entry.created_at)} · Последнее использование: {date(entry.last_used_at)}</small></div>
          {#if entry.revoked_at===null}
            {#if confirmId===entry.id}<div class="revoke-confirm"><p>Устройство потеряет доступ к библиотеке.</p><button type="button" disabled={busy} onclick={()=>revoke(entry.id)}>Отозвать токен</button><button type="button" disabled={busy} onclick={()=>confirmId=''}>Отмена</button></div>
            {:else}<button type="button" disabled={busy} aria-label={`Отозвать: ${entry.name}`} onclick={()=>confirmId=entry.id}>Отозвать</button>{/if}
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .access-panel {padding:24px;margin:0 0 28px;border:1px solid var(--border,#dce3d8);border-radius:10px;background:var(--surface,#fffefa);}
  h2 {margin:0;font:26px/1.2 Georgia,serif;}
  p {font-size:14px;line-height:1.5;}
  label {display:block;font-size:14px;margin-bottom:8px;}
  .create-fields {display:flex;gap:10px;align-items:center;}
  input {flex:1;min-width:0;box-sizing:border-box;min-height:44px;padding:10px;border:1px solid var(--border,#dce3d8);border-radius:5px;background:var(--panel,#f7f7f2);color:inherit;font:16px system-ui,sans-serif;}
  #new-access-token {font:14px monospace;}
  button {min-height:44px;padding:8px 14px;border:1px solid var(--border,#dce3d8);border-radius:5px;background:var(--panel,#f7f7f2);color:inherit;}
  button.primary {background:var(--primary,#325941);border-color:var(--primary,#325941);color:var(--on-primary,#fffef1);}
  .new-token {margin-top:20px;padding:16px;border:1px solid var(--border,#dce3d8);border-radius:6px;}
  .copy-status {margin-bottom:0;}
  ul {list-style:none;margin:24px 0 0;padding:0;}
  li {display:flex;gap:16px;align-items:center;justify-content:space-between;padding:16px 0;border-top:1px solid var(--border,#dce3d8);}
  .token-info {display:grid;gap:6px;min-width:0;overflow-wrap:anywhere;}
  .token-info span,small {font-size:13px;color:var(--muted,#667267);}
  .revoked {opacity:.65;}
  .revoke-confirm {flex-shrink:0;max-width:240px;}
  .revoke-confirm p {margin-top:0;}
  .revoke-confirm button+button {margin-left:6px;}
  @media(max-width:600px) {.access-panel{padding:16px;}.create-fields{flex-direction:column;align-items:stretch;}input{width:100%;}li{align-items:flex-start;flex-wrap:wrap;}.revoke-confirm{max-width:none;}}
</style>
