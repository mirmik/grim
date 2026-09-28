<script lang="ts">
  import type { ReaderNote } from './notes';
  let {notes,currentPageId,selection,status,oncreate,onupdate,ondelete,onopen,onclose}: {
    notes:ReaderNote[]; currentPageId:string|null; selection:string; status:Record<string,string>;
    oncreate:(text:string)=>void; onupdate:(id:string,text:string)=>void; ondelete:(id:string)=>void;
    onopen:(note:ReaderNote)=>void; onclose:()=>void;
  } = $props();
  let draft = $state(''), editing = $state<string|null>(null), editText = $state('');
  let currentNotes = $derived(notes.filter(note=>note.page_id===currentPageId));
  let otherNotes = $derived(notes.filter(note=>note.page_id!==currentPageId));
  function create() {if(!draft.trim())return;oncreate(draft.trim());draft='';}
  function startEdit(note:ReaderNote) {editing=note.id;editText=note.text;}
  function saveEdit(note:ReaderNote) {if(!editText.trim())return;onupdate(note.id,editText.trim());editing=null;}
</script>

{#snippet card(note:ReaderNote)}
  <article class="note-card" class:unresolved={status[note.id]==='missing'}>
    <button class="note-target" onclick={()=>onopen(note)}>
      <span class="note-chapter">{note.page_title}</span>
      <q>{note.anchor.exact}</q>
    </button>
    {#if editing===note.id}
      <label class="sr-only" for={`edit-${note.id}`}>Текст заметки</label>
      <textarea id={`edit-${note.id}`} bind:value={editText} maxlength="5000"></textarea>
      <div class="note-actions"><button onclick={()=>editing=null}>Отмена</button><button class="primary" disabled={!editText.trim()} onclick={()=>saveEdit(note)}>Сохранить</button></div>
    {:else}
      <p>{note.text}</p>
      {#if status[note.id]==='missing'}<div class="note-warning">Фрагмент изменился — заметка сохранена, но место нужно уточнить</div>{/if}
      <div class="note-actions"><button onclick={()=>startEdit(note)}>Изменить</button><button class="danger" onclick={()=>ondelete(note.id)}>Удалить</button></div>
    {/if}
  </article>
{/snippet}

<section class="notes-panel" aria-label="Заметки">
  <div class="panel-heading"><h2>Заметки</h2><button aria-label="Закрыть заметки" onclick={onclose}>×</button></div>
  <p class="context-note">Выделите фрагмент на странице и оставьте мысль. Привязка восстановится, даже если текст главы немного изменится.</p>
  {#if selection}
    <form class="note-form" onsubmit={(event)=>{event.preventDefault();create();}}>
      <q>{selection}</q>
      <label for="new-note">Новая заметка</label>
      <textarea id="new-note" bind:value={draft} maxlength="5000" placeholder="Что важно запомнить?"></textarea>
      <button class="primary" disabled={!draft.trim()}>Сохранить заметку</button>
    </form>
  {:else}
    <p class="empty-selection">Чтобы добавить заметку, сначала выделите текст в книге.</p>
  {/if}
  <h3>В ЭТОЙ ГЛАВЕ <span>{currentNotes.length}</span></h3>
  {#if currentNotes.length}{#each currentNotes as note (note.id)}{@render card(note)}{/each}{:else}<p class="empty-notes">Заметок в этой главе пока нет</p>{/if}
  {#if otherNotes.length}
    <h3>В ДРУГИХ ГЛАВАХ <span>{otherNotes.length}</span></h3>
    {#each otherNotes as note (note.id)}{@render card(note)}{/each}
  {/if}
</section>
