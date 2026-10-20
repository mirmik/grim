<script lang="ts">
  import { onMount } from 'svelte';
  import { normalizeServerAddress } from './server-connection';

  let address = $state(''), error = $state('');
  onMount(() => {
    try { address = localStorage.getItem('grim-server-address') || ''; } catch {}
  });
  function connect(event: SubmitEvent) {
    event.preventDefault();
    try {
      const url = normalizeServerAddress(address);
      try { localStorage.setItem('grim-server-address', url); } catch {}
      location.assign(url);
    } catch (e) { error = (e as Error).message; }
  }
</script>

<section class="server-connection" aria-labelledby="server-title">
  <h2 id="server-title">Ваша библиотека Grim</h2>
  <p>Подключитесь к своему серверу, чтобы читать книги, делать заметки и работать с агентом.</p>
  <form onsubmit={connect}>
    <label for="server-address">Адрес сервера</label>
    <div class="connection-fields">
      <input id="server-address" bind:value={address} type="url" inputmode="url" autocapitalize="none" autocomplete="url" spellcheck="false" placeholder="https://reader.example.org/grim/" required />
      <button type="submit">Подключиться</button>
    </div>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </form>
  <p class="connection-help">Адрес сохранится. Для чтения книг с сервера нужно соединение с ним. Кнопка «Назад» из библиотеки вернёт сюда — можно сменить адрес или читать книги на устройстве.</p>
</section>

<style>
  .server-connection { padding:24px; margin-bottom:32px; border:1px solid var(--border,#d3ddc7); border-radius:10px; background:var(--surface,#fffefa); }
  h2 { font:26px/1.2 Georgia,serif; margin:0 0 12px; }
  p { font-size:14px; line-height:1.6; max-width:650px; }
  label { display:block; font-size:13px; margin:20px 0 8px; }
  .connection-fields { display:flex; gap:10px; }
  input { flex:1; min-width:0; min-height:44px; padding:10px; border:1px solid var(--border,#d3ddc7); border-radius:6px; background:var(--panel,#f7f7f2); color:inherit; font:16px system-ui,sans-serif; }
  button { min-height:44px; padding:10px 18px; border:0; border-radius:6px; background:var(--primary,#325941); color:var(--on-primary,#fffef1); font-size:14px; }
  .connection-help { font-size:12px; color:var(--muted,#667267); margin:16px 0 0; }
  @media(max-width:500px) { .server-connection { padding:18px; } .connection-fields { flex-direction:column; } }
</style>
