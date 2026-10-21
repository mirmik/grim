<script lang="ts">
  import { renderAgentMarkdown } from './agent-markdown';
  let {text}=$props<{text:string}>();
  let html=$derived(renderAgentMarkdown(text));
</script>

<div class="agent-markdown">{@html html}</div>

<style>
  .agent-markdown{white-space:normal;min-width:0;line-height:1.65;overflow-wrap:anywhere}
  .agent-markdown :global(p){margin:0 0 .85em}
  .agent-markdown :global(> :last-child){margin-bottom:0}
  .agent-markdown :global(h1),.agent-markdown :global(h2),.agent-markdown :global(h3),.agent-markdown :global(h4),.agent-markdown :global(h5),.agent-markdown :global(h6){font-family:inherit;font-weight:600;line-height:1.35;margin:1.25em 0 .55em;color:inherit}
  .agent-markdown :global(h1){font-size:1.4em}.agent-markdown :global(h2){font-size:1.25em}.agent-markdown :global(h3){font-size:1.12em}.agent-markdown :global(h4),.agent-markdown :global(h5),.agent-markdown :global(h6){font-size:1em}
  .agent-markdown :global(> :first-child){margin-top:0}
  .agent-markdown :global(strong){font-weight:650}
  .agent-markdown :global(blockquote){margin:.8em 0 1em;padding:.15em 0 .15em 12px;border-left:3px solid var(--focus,#477b61);color:var(--text,#304c32)}
  .agent-markdown :global(blockquote > :last-child){margin-bottom:0}
  .agent-markdown :global(ul),.agent-markdown :global(ol){margin:.6em 0 1em;padding-left:1.55em}
  .agent-markdown :global(li){margin:.3em 0;padding-left:.1em}
  .agent-markdown :global(li > p){margin:.3em 0}
  .agent-markdown :global(li > ul),.agent-markdown :global(li > ol){margin:.25em 0}
  .agent-markdown :global(code){display:inline;max-width:none;margin:0;font: .88em/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;background:var(--hover,#eef3e5);border-radius:4px;padding:.12em .3em;white-space:break-spaces;overflow-wrap:anywhere;word-break:normal}
  .agent-markdown :global(pre){max-width:100%;box-sizing:border-box;overflow-x:auto;margin:.8em 0 1em;padding:12px;border:1px solid var(--border,#cedbbb);border-radius:6px;background:var(--surface,#fffefa);white-space:pre;tab-size:2}
  .agent-markdown :global(pre code){font-size:.85em;background:transparent;padding:0;border-radius:0;white-space:pre;overflow-wrap:normal;word-break:normal}
  .agent-markdown :global(a){color:var(--text,#355b3b);text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere}
  .agent-markdown :global(a:focus-visible),.agent-markdown :global(.agent-table:focus-visible){outline:2px solid var(--focus,#477b61);outline-offset:2px}
  .agent-markdown :global(hr){border:0;border-top:1px solid var(--border,#cedbbb);margin:1.2em 0}
  .agent-markdown :global(.agent-table){max-width:100%;overflow-x:auto;margin:.8em 0 1em}
  .agent-markdown :global(table){border-collapse:collapse;width:100%;font-size:.92em}
  .agent-markdown :global(th),.agent-markdown :global(td){border:1px solid var(--border,#cedbbb);padding:7px 9px;text-align:left;min-width:90px;vertical-align:top}
  .agent-markdown :global(th){font-weight:600;background:var(--hover,#eef3e5)}
  .agent-markdown :global([align="center"]){text-align:center}.agent-markdown :global([align="right"]){text-align:right}
</style>
