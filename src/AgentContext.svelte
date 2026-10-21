<script lang="ts">
  type Request = {model?:string;messages?:unknown[];tools?:unknown[];[key:string]:unknown};
  type Context = {snapshot:{book:{title:string;subtitle:string;description:string;version:string;view_title:string};page:{title:string}|null};
    preview:Request;last_request:{request:Request;created_at:number;step:number}|null;draft_empty:boolean};
  let {data,loading,onrefresh,onclose}=$props<{data:Context;loading:boolean;onrefresh:()=>void;onclose:()=>void}>();
  let view=$state<'sent'|'preview'>('sent');
  let sent=$derived(view==='sent' && !!data.last_request);
  let request=$derived(sent?data.last_request!.request:data.preview);
</script>

<section class="agent-debug" aria-label="Контекст агента">
  <div class="debug-heading"><h3>Контекст агента</h3><button onclick={onclose} aria-label="Вернуться к чату">×</button></div>
  <details class="book-summary" open>
    <summary>Сейчас открыта: {data.snapshot.book.title}</summary>
    {#if data.snapshot.book.subtitle}<p>{data.snapshot.book.subtitle}</p>{/if}
    <p>{data.snapshot.book.version==='source'?'Оригинал':data.snapshot.book.view_title} · {data.snapshot.page?.title||'Без открытой страницы'}</p>
    <p>{data.snapshot.book.description||'Аннотация в книге не указана.'}</p>
  </details>
  <div class="debug-actions">
    <button aria-pressed={sent} disabled={!data.last_request} onclick={()=>view='sent'}>Последний отправленный</button>
    <button aria-pressed={!sent} onclick={()=>view='preview'}>Следующий запрос</button>
    <button disabled={loading} onclick={onrefresh}>{loading?'Обновляем…':'Обновить контекст'}</button>
  </div>
  {#if sent}
    <p class="debug-note">Фактически передан модели {new Date(data.last_request!.created_at*1000).toLocaleString('ru-RU')}, шаг {data.last_request!.step}. Последний ответ модели может ещё не входить в этот запрос.</p>
  {:else}
    <p class="debug-note">Предпросмотр с текущими настройками, историей и местом чтения. {data.draft_empty?'Сообщение ещё не введено.':'Включает черновик сообщения.'} Модели ничего не отправляется.</p>
  {/if}
  <p class="debug-note">Модель: {request.model} · Сообщений: {request.messages?.length||0} · Инструментов: {request.tools?.length||0}</p>
  <textarea class="model-context" readonly rows="24" aria-label={sent?'Последний запрос модели':'Предпросмотр запроса модели'} value={JSON.stringify(request,null,2)}></textarea>
</section>

<style>
  .agent-debug { min-height:0; overflow:auto; flex:1; padding-top:12px; }
  .debug-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
  h3 { font:20px Georgia,serif; margin:0; }
  button { border:1px solid var(--border,#cbd8bc); border-radius:5px; background:var(--panel,#f8f9f2); color:var(--text,#355b3b); padding:8px; font-size:11px; min-height:36px; }
  button[aria-pressed="true"] { background:var(--hover,#eef3e5); border-color:var(--focus,#477b61); }
  .debug-heading button { font-size:22px; border:0; background:transparent; }
  .debug-actions { display:flex; flex-wrap:wrap; gap:6px; margin:14px 0; }
  .debug-note,.book-summary p { font-size:12px; line-height:1.6; color:var(--muted,#66765d); overflow-wrap:anywhere; }
  .book-summary { margin:12px 0; padding:12px 0; }
  .book-summary summary { line-height:1.5; overflow-wrap:anywhere; }
  textarea { display:block; width:100%; resize:vertical; min-height:240px; font:11px/1.6 ui-monospace,monospace; padding:12px; border:1px solid var(--border,#cbd8bc); border-radius:6px; background:var(--surface,#fffefa); color:var(--text,#263c34); white-space:pre-wrap; overflow-wrap:anywhere; }
</style>
