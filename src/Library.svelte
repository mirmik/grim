<script lang="ts">
  import ThemePicker from './ThemePicker.svelte';
  import { onMount } from 'svelte';
  import { appPath, offline, fetchLibrary } from './platform';
  let {onopen}: {onopen:(id:string)=>void} = $props();
  type Entry = {id:string;title:string;subtitle:string;root:string;page_count:number;error:string|null};
  let books = $state<Entry[]>([]), loading = $state(true), error = $state(''), busy = $state(false);
  let mode = $state<'create'|'add'|'import-epub'|null>(null), title = $state(''), root = $state(''), newRoot = $state('');
  let epub = $state<File|null>(null);
  let token = '';
  async function refresh() {
    try {
      const response = await fetchLibrary();
      if (!response.ok) throw new Error('Не удалось загрузить библиотеку');
      const data = await response.json();books=data.books;token=data.writer_token;newRoot=data.new_books_root;error='';
    } catch(e) {error=String(e);} finally {loading=false;}
  }
  async function submit(event:SubmitEvent) {
    event.preventDefault(); if (!mode || busy) return;
    busy=true;error='';
    try {
      // Refresh the ephemeral viewer credential if the local server was restarted.
      const bootstrap = await fetchLibrary();
      if (!bootstrap.ok) throw new Error('Нет соединения с библиотекой');
      token=(await bootstrap.json()).writer_token;
      if(mode==='import-epub' && (!epub || epub.size>64*1024*1024)) throw new Error('Выберите EPUB размером до 64 МБ');
      const response=await fetch(`/api/library/${mode}`,{method:'POST',headers:{'Content-Type':mode==='import-epub'?'application/epub+zip':'application/json','X-Grim-Viewer':token},body:mode==='import-epub'?epub:JSON.stringify(mode==='create'?{title:title.trim()}:{root:root.trim()})});
      const data=await response.json();
      if (!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Проверьте название или путь к папке');
      onopen(data.id);
    } catch(e) {error=String(e);} finally {busy=false;}
  }
  onMount(()=>{void refresh();});
</script>

<div class="library-shell">
  <header class="library-header"><a class="brand" href={appPath} aria-label="Grim, библиотека"><span class="brand-mark">g</span><span>grim<span class="brand-period">.</span></span></a><span>ВАША БИБЛИОТЕКА</span><ThemePicker/></header>
  <main class="library-main">
    <div class="library-intro"><div><p class="eyebrow">ПРОСТРАНСТВО ДЛЯ ЛЮБОПЫТСТВА</p><h1>Каждая книга —<br>новое начало.</h1><p>Возвращайтесь к знакомым идеям или начните исследовать что-то новое.</p></div>{#if !offline}<div class="library-actions"><button class="primary" disabled={busy} onclick={()=>{mode='create';error='';}}>+ Новая книга</button><button disabled={busy} onclick={()=>{mode='import-epub';error='';}}>Импорт EPUB</button><button disabled={busy} onclick={()=>{mode='add';error='';}}>Добавить папку</button></div>{/if}</div>
    {#if mode}
      <form class="book-form" onsubmit={submit}>
        <div class="panel-heading"><h2>{mode==='create'?'Новая пустая книга':mode==='import-epub'?'Импортировать EPUB':'Подключить существующую книгу'}</h2><button type="button" aria-label="Закрыть форму" disabled={busy} onclick={()=>mode=null}>×</button></div>
        {#if mode==='create'}<label for="book-title">Название книги</label><input id="book-title" bind:value={title} maxlength="200" placeholder="Например, Геометрия пространства" required><p>Создадим отдельную папку и пустое оглавление. Первые страницы вы сможете написать со своим агентом.</p><details><summary>Где будет храниться книга</summary><code>{newRoot}</code></details>
        {:else if mode==='import-epub'}<label for="book-epub">Файл EPUB</label><input id="book-epub" type="file" accept=".epub,application/epub+zip" disabled={busy} onchange={event=>epub=event.currentTarget.files?.[0]??null} required><p>Разделим книгу на небольшие страницы, сохраним иллюстрации и оглавление. Текст можно будет читать и редактировать с агентом. До 64 МБ.</p>
        {:else}<label for="book-root">Путь к папке на этом компьютере</label><input id="book-root" bind:value={root} placeholder="/home/…/моя-книга" required><p>Укажите абсолютный путь к папке с book.json. Книга останется на своём месте; файлы не копируются.</p>{/if}
        <button class="primary" type="submit" disabled={busy || (mode==='create'?!title.trim():mode==='import-epub'?!epub:!root.trim())}>{busy?(mode==='import-epub'?'Импортируем…':'Сохраняем…'):mode==='create'?'Создать книгу':mode==='import-epub'?'Импортировать книгу':'Подключить папку'}</button>
      </form>
    {/if}
    {#if error}<div class="error" role="alert">{error}</div>{/if}
    <div class="shelf-heading"><span>КНИГИ <b>{books.length.toString().padStart(2,'0')}</b></span><button disabled={loading} onclick={()=>refresh()}>Обновить список ↻</button></div>
    {#if loading}<p>Открываем библиотеку…</p>{:else}<div class="book-grid">{#each books as book,i}
      <article class="book-card" class:unavailable={Boolean(book.error)}><div class="book-card-top"><span class="book-monogram">{book.title.slice(0,1).toUpperCase()}</span><span>{String(i+1).padStart(2,'0')} / GRIM</span></div><h2>{book.title}</h2><p class="card-subtitle">{book.subtitle || (book.page_count?'Книга из локальной папки':'Чистое место для первой мысли')}</p><p class="card-count">{book.page_count} стр.</p>{#if book.error}<p class="card-error">{book.error}</p>{/if}{#if !offline}<details><summary>Папка книги</summary><code>{book.root}</code></details>{:else}<p class="offline-book-label">Доступна без сети</p>{/if}<button class="open-book" onclick={()=>onopen(book.id)}>Открыть книгу <span>↗</span></button></article>
    {/each}</div>{/if}
    <p class="library-footnote">{offline ? 'Книги уже на устройстве. Читайте без интернета — ваше место сохранится. Новые книги и обновления пока добавляются вместе с приложением.' : 'Ваши книги — обычные папки. Внешний агент пишет страницы, Grim помогает их читать.'}</p>
  </main>
</div>

<style>
  .library-actions { flex-wrap: wrap; flex-shrink: 1; }
</style>
